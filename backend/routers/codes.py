"""공통 코드 마스터 — SCR-14 공통 코드 관리 (tb_code).

화면에서 추가·수정·비활성 가능한 분류값을 관리한다. 첫 대상은 고객사 구분
(category=CLIENT_TYPE, 운수사/건물·농장). 향후 자산 유형 등도 같은 API로 확장.

설계 원칙(데이터 정합성):
- code(코드값)는 생성 후 불변 — 기존 레코드가 저장한 값이 깨지지 않도록.
- label(표시명)만 자유 수정 — 이름 변경이 기존 데이터에 안전.
- 사용 중(참조 레코드 존재)인 코드는 삭제 불가 → 비활성(active=N)만 허용.
- 내장 코드(is_system=Y)는 삭제 불가(비활성만).
- 조회는 인증 사용자 전체(드롭다운용), 변경은 ADMIN 전용(§10.1).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_role
from models import Client, Code, User, get_db
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/codes", tags=["codes"])

# 관리 대상 카테고리 라벨 (화면 표기·확장 지점)
CATEGORY_LABELS = {
    "CLIENT_TYPE": "고객사 구분",
}

# 코드 사용처 매핑 — 삭제 가능 판단(참조 카운트)용.
# category -> (참조 모델, 코드값을 담는 컬럼명)
USAGE_REFS = {
    "CLIENT_TYPE": (Client, "client_type"),
}


def _usage_count(db: Session, category: str, code: str) -> int:
    """해당 코드값을 사용 중인 레코드 수 (삭제 가능 판단)."""
    ref = USAGE_REFS.get(category)
    if ref is None:
        return 0
    model, column = ref
    return db.query(model).filter(getattr(model, column) == code).count()


def _code_out(db: Session, row: Code, with_usage: bool = False) -> schemas.CodeOut:
    out = schemas.CodeOut.model_validate(row, from_attributes=True)
    if with_usage:
        out = out.model_copy(update={"usage_count": _usage_count(db, row.category, row.code)})
    return out


@router.get("", response_model=List[schemas.CodeOut])
def list_codes(
    category: str = Query(..., description="코드 카테고리 (예: CLIENT_TYPE)"),
    include_inactive: bool = Query(
        False, description="비활성 코드 포함 여부(관리 화면=true, 드롭다운=false)"
    ),
    with_usage: bool = Query(False, description="사용 중 레코드 수 포함(관리 화면용)"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """카테고리별 코드 목록 — sort_order·code 순. 드롭다운/관리 화면 공용."""
    query = db.query(Code).filter(Code.category == category)
    if not include_inactive:
        query = query.filter(Code.active == "Y")
    rows = query.order_by(Code.sort_order.asc(), Code.code.asc()).all()
    return [_code_out(db, row, with_usage=with_usage) for row in rows]


@router.post("", response_model=schemas.CodeOut, status_code=201)
def create_code(
    payload: schemas.CodeCreate,
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """코드 추가 (ADMIN). 같은 카테고리 내 code 중복 금지."""
    code = payload.code.strip().upper()
    exists = (
        db.query(Code)
        .filter(Code.category == payload.category, Code.code == code)
        .first()
    )
    if exists is not None:
        raise HTTPException(status_code=409, detail="이미 존재하는 코드값입니다: {0}".format(code))
    row = Code(
        category=payload.category.strip(),
        code=code,
        label=payload.label.strip(),
        sort_order=payload.sort_order,
        active="Y",
        is_system="N",
    )
    db.add(row)
    db.flush()
    AuditLogger.code_change(
        db, admin.user_id, "CODE_CREATE", row.code_id,
        new_value="{0}:{1} ({2})".format(row.category, row.code, row.label),
    )
    db.commit()
    db.refresh(row)
    return _code_out(db, row, with_usage=True)


@router.put("/{code_id}", response_model=schemas.CodeOut)
def update_code(
    code_id: str,
    payload: schemas.CodeUpdate,
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """코드 수정 (ADMIN) — label·정렬·활성만. code값·category는 불변."""
    row = db.get(Code, code_id)
    if row is None:
        raise HTTPException(status_code=404, detail="코드를 찾을 수 없습니다")

    before = "{0} / active={1} / sort={2}".format(row.label, row.active, row.sort_order)
    if payload.label is not None:
        row.label = payload.label.strip()
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order
    if payload.active is not None:
        row.active = payload.active
    after = "{0} / active={1} / sort={2}".format(row.label, row.active, row.sort_order)

    AuditLogger.code_change(
        db, admin.user_id, "CODE_UPDATE", row.code_id, old_value=before, new_value=after
    )
    db.commit()
    db.refresh(row)
    return _code_out(db, row, with_usage=True)


@router.delete("/{code_id}", status_code=204)
def delete_code(
    code_id: str,
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """코드 삭제 (ADMIN). 내장 코드·사용 중 코드는 삭제 불가 → 비활성 사용."""
    row = db.get(Code, code_id)
    if row is None:
        raise HTTPException(status_code=404, detail="코드를 찾을 수 없습니다")
    if row.is_system == "Y":
        raise HTTPException(
            status_code=409,
            detail="내장 코드는 삭제할 수 없습니다. 사용을 중단하려면 '비활성'으로 전환하세요.",
        )
    used = _usage_count(db, row.category, row.code)
    if used > 0:
        raise HTTPException(
            status_code=409,
            detail="이 구분을 사용 중인 고객사가 {0}곳 있어 삭제할 수 없습니다. "
            "'비활성'으로 전환하면 신규 선택에서 숨겨지고 기존 데이터는 유지됩니다.".format(used),
        )
    AuditLogger.code_change(
        db, admin.user_id, "CODE_DELETE", row.code_id,
        old_value="{0}:{1} ({2})".format(row.category, row.code, row.label),
    )
    db.delete(row)
    db.commit()
    return None


def validate_active_code(db: Session, category: str, code: Optional[str]) -> None:
    """고객사 등록/수정 등에서 client_type 유효성 검증 — 활성 코드만 허용.

    구분 정규식 하드코딩을 대체한다(422 대신 명확한 메시지). code가 None이면 통과.
    """
    if code is None:
        return
    row = (
        db.query(Code)
        .filter(Code.category == category, Code.code == code, Code.active == "Y")
        .first()
    )
    if row is None:
        label = CATEGORY_LABELS.get(category, category)
        raise HTTPException(
            status_code=422,
            detail="유효하지 않은 {0} 값입니다: '{1}'. 환경설정 > 공통 코드 관리에서 확인하세요.".format(
                label, code
            ),
        )
