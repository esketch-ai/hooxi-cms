"""감사 로그 조회 — SCR-14 감사 로그 탭 (tb_audit_log, ADMIN 전용).

알려진 action 유형: REVEAL_AUTH / SETTLEMENT_CHANGE / REPORT_VIEW /
KAKAO_APPROVAL / CONFIG_CHANGE. 로그 적재는 각 도메인 라우터가 담당하며
여기서는 조회(필터·페이지네이션·actor 이름 조인)만 제공한다.
"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import schemas
from auth import require_role
from models import AuditLog, User, get_db
from routers import common

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=schemas.AuditLogListResponse)
def list_audit_logs(
    action: Optional[str] = Query(
        None, description="REVEAL_AUTH/SETTLEMENT_CHANGE/REPORT_VIEW/KAKAO_APPROVAL/CONFIG_CHANGE"
    ),
    target_type: Optional[str] = Query(None, description="대상 유형 (ASSET/CONFIG/REPORT 등)"),
    actor_id: Optional[str] = Query(None, description="행위자 user_id"),
    date_from: Optional[date] = Query(None, description="기간 시작"),
    date_to: Optional[date] = Query(None, description="기간 끝"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """감사 로그 목록 — action·target_type·기간·actor 필터 + 페이지네이션 (최근순)."""
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if target_type:
        query = query.filter(AuditLog.target_type == target_type)
    if actor_id:
        query = query.filter(AuditLog.actor_id == actor_id)
    if date_from:
        query = query.filter(AuditLog.created_at >= common.kst_day_start_utc(date_from))
    if date_to:
        query = query.filter(AuditLog.created_at <= common.kst_day_end_utc(date_to))

    total = query.count()
    rows = (
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    unames = common.user_name_map(db, [log.actor_id for log in rows])
    items = [
        schemas.AuditLogOut.model_validate(log, from_attributes=True).model_copy(
            update={"actor_name": unames.get(log.actor_id)}
        )
        for log in rows
    ]
    return schemas.AuditLogListResponse(items=items, total=total)
