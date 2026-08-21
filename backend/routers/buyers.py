"""매수자 마스터 — 증권/투자/금융사 신원의 근본(Phase 4 INC-1, 부록 N.8 D1).

거래계약(ProjectSale)이 buyer_id로 참조하는 마스터. 기존 buyer_name(free-text)은 전환기
동안 유지하고, 이 마스터로 신원을 일원화한다(비파괴 additive).

- 조회: 인증 사용자 전체(드롭다운용). 변경: master.write 권한.
- buyer_type은 SALE_BUYER_TYPE 공통코드 재사용(validate_active_code).
- name 유일(uq_buyer_name) — 중복 시 409.
- 삭제 시 ProjectSale.buyer_id는 FK ondelete=SET NULL로 자동 해제(거래계약 자체는 보존).
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from sqlalchemy import distinct, func

from models import Buyer, ProjectSale, User, get_db
from routers import common
from routers.codes import validate_active_code
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/buyers", tags=["buyers"])

# 등록/수정에서 그대로 반영하는 필드(name·buyer_type은 별도 검증 후 반영)
_BUYER_FIELDS = (
    "name", "buyer_type", "biz_reg_no",
    "contact_name", "contact_phone", "contact_email", "memo",
)


def _check_name_duplicate(db: Session, name: str, exclude_buyer_id: Optional[str] = None):
    """매수자명 중복 검사 — 공백 제거·casefold 정규화 비교(uq_buyer_name 방어선)."""
    normalized = (name or "").strip().casefold()
    if not normalized:
        return
    query = db.query(Buyer)
    if exclude_buyer_id:
        query = query.filter(Buyer.buyer_id != exclude_buyer_id)
    for other in query.all():
        if (other.name or "").strip().casefold() == normalized:
            raise HTTPException(
                status_code=409,
                detail="이미 등록된 매수자명입니다 (기존: {0})".format(other.name),
            )


@router.get("", response_model=schemas.BuyerListResponse)
def list_buyers(
    q: Optional[str] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """매수자 목록 — name ilike 검색 + 페이지네이션(등록순)."""
    query = db.query(Buyer)
    if q:
        query = query.filter(
            Buyer.name.ilike("%{0}%".format(common.escape_like(q)), escape="\\")
        )
    total = query.count()
    rows = (
        query.order_by(Buyer.created_at.asc(), Buyer.buyer_id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    # 참여 사업 수 — 거래계약(ProjectSale.buyer_id) distinct 사업 집계(1쿼리, N+1 방지).
    # "매수자는 거래계약으로 사업에 참여한다"는 흐름을 목록에서 바로 인지시키는 용도.
    ids = [b.buyer_id for b in rows]
    counts = {}
    if ids:
        counts = dict(
            db.query(ProjectSale.buyer_id, func.count(distinct(ProjectSale.project_id)))
            .filter(ProjectSale.buyer_id.in_(ids))
            .group_by(ProjectSale.buyer_id)
            .all()
        )
    return schemas.BuyerListResponse(
        items=[
            schemas.BuyerOut.model_validate(b, from_attributes=True).model_copy(
                update={"project_count": int(counts.get(b.buyer_id, 0))}
            )
            for b in rows
        ],
        total=total,
    )


@router.post("", response_model=schemas.BuyerOut, status_code=201)
def create_buyer(
    payload: schemas.BuyerIn,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """매수자 등록 — buyer_type은 SALE_BUYER_TYPE 공통코드 검증, name 중복 409."""
    if payload.buyer_type:
        validate_active_code(db, "SALE_BUYER_TYPE", payload.buyer_type)
    _check_name_duplicate(db, payload.name)
    buyer = Buyer(**{f: getattr(payload, f) for f in _BUYER_FIELDS})
    db.add(buyer)
    db.flush()  # PK(gen_uuid) 확보 — 감사 대상 ID
    AuditLogger.log_action(
        db,
        user.user_id,
        "BUYER_CREATE",
        target_type="BUYER",
        target_id=buyer.buyer_id,
    )
    db.commit()
    db.refresh(buyer)
    return schemas.BuyerOut.model_validate(buyer, from_attributes=True)


@router.get("/{buyer_id}", response_model=schemas.BuyerOut)
def get_buyer(
    buyer_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """매수자 상세."""
    buyer = common.get_or_404(db, Buyer, buyer_id, "매수자")
    return schemas.BuyerOut.model_validate(buyer, from_attributes=True)


@router.put("/{buyer_id}", response_model=schemas.BuyerOut)
def update_buyer(
    buyer_id: str,
    payload: schemas.BuyerUpdate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """매수자 수정 — 전달된 필드만 반영."""
    buyer = common.get_or_404(db, Buyer, buyer_id, "매수자")
    data = payload.model_dump(exclude_unset=True)
    if data.get("buyer_type"):
        validate_active_code(db, "SALE_BUYER_TYPE", data["buyer_type"])
    if "name" in data:
        _check_name_duplicate(db, data["name"], exclude_buyer_id=buyer_id)
    for field in _BUYER_FIELDS:
        if field in data:
            setattr(buyer, field, data[field])
    AuditLogger.log_action(
        db,
        user.user_id,
        "BUYER_UPDATE",
        target_type="BUYER",
        target_id=buyer.buyer_id,
    )
    db.commit()
    db.refresh(buyer)
    return schemas.BuyerOut.model_validate(buyer, from_attributes=True)


@router.delete("/{buyer_id}", response_model=schemas.MessageResponse)
def delete_buyer(
    buyer_id: str,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """매수자 삭제 — 거래계약의 buyer_id는 FK ondelete=SET NULL로 자동 해제(계약 보존).

    단, 활성 INVESTOR 외부 포털 계정이 연결된 경우 삭제 차단(409): SET NULL로 계정의
    열람 스코프가 조용히 끊기는 사고 방지(먼저 계정 비활성화를 요구). 계약(ProjectSale)은
    buyer_name이 남으므로 SET NULL 허용, 포털 계정만 보호한다.
    """
    buyer = common.get_or_404(db, Buyer, buyer_id, "매수자")
    linked_account = (
        db.query(User.user_id)
        .filter(
            User.buyer_id == buyer_id,
            User.role == "INVESTOR",
            User.status != "INACTIVE",
        )
        .first()
    )
    if linked_account:
        raise HTTPException(
            status_code=409,
            detail="이 매수자에 연결된 외부 포털 계정(투자·금융사)이 있어 삭제할 수 없습니다. 먼저 해당 계정을 비활성화하세요.",
        )
    db.delete(buyer)
    AuditLogger.log_action(
        db,
        user.user_id,
        "BUYER_DELETE",
        target_type="BUYER",
        target_id=buyer_id,
    )
    db.commit()
    return schemas.MessageResponse(message="매수자가 삭제되었습니다")
