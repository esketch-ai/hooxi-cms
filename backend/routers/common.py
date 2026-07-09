"""P1 라우터 공용 헬퍼 — 이름 조인·기간 파싱·응답 빌더."""

import re
from calendar import monthrange
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

import schemas
from models import Client, Document, User, utcnow

# 자동 적재 표식 — 보고서 발송·일정 완료로 생성된 활동 이력의 제목 접두어
AUTO_PREFIX = "[자동]"

_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def current_period() -> str:
    return utcnow().strftime("%Y-%m")


def validate_period(period: str) -> str:
    if not _PERIOD_RE.match(period or ""):
        raise HTTPException(status_code=422, detail="period는 YYYY-MM 형식이어야 합니다")
    return period


def period_bounds(period: str) -> Tuple[datetime, datetime]:
    """'YYYY-MM' → (월초 00:00:00, 말일 23:59:59)."""
    year, month = int(period[:4]), int(period[5:7])
    last_day = monthrange(year, month)[1]
    return datetime(year, month, 1), datetime(year, month, last_day, 23, 59, 59)


def get_or_404(db: Session, model, pk: Optional[str], label: str):
    obj = db.get(model, pk) if pk else None
    if obj is None:
        raise HTTPException(status_code=404, detail="{0}을(를) 찾을 수 없습니다".format(label))
    return obj


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
