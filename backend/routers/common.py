"""P1 라우터 공용 헬퍼 — 이름 조인·기간 파싱·응답 빌더."""

import re
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

import schemas
from models import Client, Document, User, utcnow

# 자동 적재 표식 — 보고서 발송·일정 완료로 생성된 활동 이력의 제목 접두어
AUTO_PREFIX = "[자동]"

_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


# KST(UTC+9, DST 없음) — 사용자가 고른 '날짜'를 UTC 저장 타임스탬프와 비교할 때 사용.
# created_at 등 서버 생성 시각(UTC 저장) 필터에만 적용한다. 사용자가 벽시계로 입력한
# activity_date·schedule 일시는 저장값 자체가 KST라 이 변환을 쓰면 안 된다.
_KST_OFFSET = timedelta(hours=9)


def kst_day_start_utc(d: date) -> datetime:
    """KST 기준 해당 날짜 00:00 → UTC naive (저장 규약과 동일)."""
    return datetime.combine(d, time.min) - _KST_OFFSET


def kst_day_end_utc(d: date) -> datetime:
    """KST 기준 해당 날짜 23:59:59.999999 → UTC naive."""
    return datetime.combine(d, time.max) - _KST_OFFSET


def now_kst() -> datetime:
    """KST 벽시계 현재 시각 (naive) — utcnow()+9h.

    저장 규약: activity_date·due_date 등 사용자가 벽시계로 입력하는 필드는
    저장값 자체가 KST 벽시계이므로, 자동 적재도 반드시 이 함수를 쓴다.
    created_at 등 서버 생성 시각(naive UTC 저장)은 utcnow()를 그대로 쓴다.
    """
    return utcnow() + _KST_OFFSET


def current_period() -> str:
    """KST 벽시계 기준 당월 'YYYY-MM'.

    UTC 기준으로 계산하면 월초 00~09시(KST)에 전월로 밀린다 — 대시보드·보고서
    generate 기본값·배치가 모두 이 함수를 공유해 '당월' 기준을 KST로 통일한다.
    """
    return now_kst().strftime("%Y-%m")


def previous_period(period: str) -> str:
    """'YYYY-MM' 1개월 감산 — 배치 기본 발송 대상(전월) 계산."""
    year, month = int(period[:4]), int(period[5:7])
    if month == 1:
        return "{0}-12".format(year - 1)
    return "{0}-{1:02d}".format(year, month - 1)


def validate_period(period: str) -> str:
    if not _PERIOD_RE.match(period or ""):
        raise HTTPException(status_code=422, detail="period는 YYYY-MM 형식이어야 합니다")
    return period


def period_bounds(period: str) -> Tuple[datetime, datetime]:
    """'YYYY-MM' → (월초 00:00:00, 말일 23:59:59)."""
    year, month = int(period[:4]), int(period[5:7])
    last_day = monthrange(year, month)[1]
    return datetime(year, month, 1), datetime(year, month, last_day, 23, 59, 59)


def escape_like(value: str) -> str:
    """LIKE/ILIKE 검색어 이스케이프 — %·_·\\가 와일드카드로 해석되지 않게 리터럴로 고정.

    사용처는 반드시 ilike(..., escape="\\\\")를 함께 지정한다(방언 공통).
    예: Client.company_name.ilike("%{0}%".format(escape_like(s)), escape="\\\\")
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def josa(word: str, with_batchim: str, without_batchim: str) -> str:
    """한글 받침 유무로 조사 선택 (예: josa("고객사","을","를")→"를").

    마지막 글자가 완성형 한글이면 받침 유무로 판별, 아니면(영문·숫자 등) 둘 다 표기하는
    안전 폴백("을(를)")을 쓴다.
    """
    if not word:
        return with_batchim
    code = ord(word[-1])
    if 0xAC00 <= code <= 0xD7A3:  # 완성형 한글 음절
        return with_batchim if (code - 0xAC00) % 28 else without_batchim
    return "{0}({1})".format(with_batchim, without_batchim)


def get_or_404(db: Session, model, pk: Optional[str], label: str):
    obj = db.get(model, pk) if pk else None
    if obj is None:
        raise HTTPException(
            status_code=404,
            detail="{0}{1} 찾을 수 없습니다".format(label, josa(label, "을", "를")),
        )
    return obj


def normalize_biz_no(value: Optional[str]) -> str:
    """사업자번호 정규화 — 숫자만 추출 (하이픈·공백 등 표기 차이 무시 비교용, P1-C).

    clients.py에서 승격 — 단건 등록과 엑셀 일괄 등록(services/excel_import.py)이 공유.
    """
    return re.sub(r"\D", "", value or "")


def check_biz_reg_no_duplicate(
    db: Session, biz_reg_no: Optional[str], exclude_client_id: Optional[str] = None
):
    """사업자번호 중복 검사 (P1-C) — 정규화(숫자만) 기준 비교, 컬럼 원문은 유지.

    빈 값/None은 검사 제외. update 시 자기 자신은 exclude_client_id로 제외.
    기존 데이터가 하이픈 유무 등 표기가 달라도 잡히도록 DB LIKE가 아닌
    파이썬 정규화 비교(내부 CMS 규모라 전건 스캔 허용).
    clients.py에서 승격 — 단건 등록과 엑셀 일괄 등록이 같은 규칙을 공유.
    """
    normalized = normalize_biz_no(biz_reg_no)
    if not normalized:
        return
    query = db.query(Client).filter(Client.biz_reg_no.isnot(None))
    if exclude_client_id:
        query = query.filter(Client.client_id != exclude_client_id)
    for other in query.all():
        if normalize_biz_no(other.biz_reg_no) == normalized:
            raise HTTPException(
                status_code=409,
                detail="이미 등록된 사업자번호입니다 (기존: {0})".format(other.company_name),
            )


# 예상 정산액 상한 — 컬럼 Numeric(15,2)(정수부 13자리)의 저장 가능 한계 (#6 P2)
EXPECTED_AMOUNT_LIMIT = 1e13


def compute_expected_amount(expected_credits, allocation_ratio, unit_price, success_fee_rate):
    """§10.3 정산 산식 — 예상 정산액 = 예상 발행량(tCO₂) × 배분율(%) × 단가 × 성공 보수율(%).

    구성 요소가 하나라도 없으면(특히 단가 미입력) None → 프론트 '미정' 표시.
    """
    values = (expected_credits, allocation_ratio, unit_price, success_fee_rate)
    if any(v is None for v in values):
        return None
    return round(
        float(expected_credits)
        * (float(allocation_ratio) / 100.0)
        * float(unit_price)
        * (float(success_fee_rate) / 100.0),
        2,
    )


def validate_expected_amount(amount):
    """산식 결과가 Numeric(15,2)에 못 들어가면 422 (#6 P2) — DB 오류(500) 사전 차단.

    단가·발행량 변경, 매핑 등록 등 expected_amount를 적재하는 모든 입력 경로에서
    저장 직전에 호출한다(입력 시점 차단 우선)."""
    if amount is not None and abs(amount) >= EXPECTED_AMOUNT_LIMIT:
        raise HTTPException(
            status_code=422,
            detail="예상 정산액이 허용 범위를 초과합니다 — 단가·발행량 단위를 확인하세요",
        )
    return amount


def user_name_map(db: Session, user_ids: Iterable[Optional[str]]) -> Dict[str, str]:
    ids = {uid for uid in user_ids if uid}
    if not ids:
        return {}
    rows = db.query(User.user_id, User.name).filter(User.user_id.in_(ids)).all()
    return {uid: name for uid, name in rows}


def client_name_map(db: Session, client_ids: Iterable[Optional[str]]) -> Dict[str, str]:
    ids = {cid for cid in client_ids if cid}
    if not ids:
        return {}
    rows = db.query(Client.client_id, Client.company_name).filter(Client.client_id.in_(ids)).all()
    return {cid: name for cid, name in rows}


# ---------------------------------------------------------------------------
# 응답 빌더
# ---------------------------------------------------------------------------
def build_history_outs(db: Session, rows: List) -> List[schemas.HistoryOut]:
    unames = user_name_map(db, [h.manager_id for h in rows] + [h.created_by for h in rows])
    cnames = client_name_map(db, [h.client_id for h in rows])
    outs = []
    for h in rows:
        out = schemas.HistoryOut.model_validate(h, from_attributes=True)
        outs.append(
            out.model_copy(
                update={
                    "client_name": cnames.get(h.client_id),
                    "manager_name": unames.get(h.manager_id),
                    "created_by_name": unames.get(h.created_by),
                    "is_auto": (h.title or "").startswith(AUTO_PREFIX),
                }
            )
        )
    return outs


def build_comment_outs(db: Session, rows: List) -> List[schemas.CommentOut]:
    unames = user_name_map(db, [c.manager_id for c in rows])
    return [
        schemas.CommentOut.model_validate(c, from_attributes=True).model_copy(
            update={"manager_name": unames.get(c.manager_id)}
        )
        for c in rows
    ]


def build_schedule_outs(db: Session, rows: List) -> List[schemas.ScheduleOut]:
    unames = user_name_map(db, [s.manager_id for s in rows])
    cnames = client_name_map(db, [s.client_id for s in rows])
    return [
        schemas.ScheduleOut.model_validate(s, from_attributes=True).model_copy(
            update={
                "client_name": cnames.get(s.client_id),
                "manager_name": unames.get(s.manager_id),
            }
        )
        for s in rows
    ]


def build_document_outs(db: Session, rows: List) -> List[schemas.DocumentOut]:
    unames = user_name_map(db, [d.uploaded_by for d in rows])
    cnames = client_name_map(db, [d.client_id for d in rows])
    return [
        schemas.DocumentOut.model_validate(d, from_attributes=True).model_copy(
            update={
                "client_name": cnames.get(d.client_id),
                "uploaded_by_name": unames.get(d.uploaded_by),
            }
        )
        for d in rows
    ]


def build_report_rows(db: Session, rows: List) -> List[schemas.ReportRow]:
    unames = user_name_map(db, [r.manager_id for r in rows])
    client_ids = {r.client_id for r in rows}
    clients = (
        db.query(Client.client_id, Client.company_name, Client.client_type)
        .filter(Client.client_id.in_(client_ids))
        .all()
        if client_ids
        else []
    )
    cmap = {cid: (name, ctype) for cid, name, ctype in clients}

    doc_ids = {r.doc_id for r in rows if r.doc_id}
    docs = db.query(Document).filter(Document.doc_id.in_(doc_ids)).all() if doc_ids else []
    doc_outs = {d.doc_id: o for d, o in zip(docs, build_document_outs(db, docs))}

    outs = []
    for r in rows:
        name, ctype = cmap.get(r.client_id, (None, None))
        out = schemas.ReportRow.model_validate(r, from_attributes=True)
        outs.append(
            out.model_copy(
                update={
                    "client_name": name,
                    "client_type": ctype,
                    "manager_name": unames.get(r.manager_id),
                    "latest_doc": doc_outs.get(r.doc_id),
                }
            )
        )
    return outs
