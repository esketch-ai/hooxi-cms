"""감사 로그 조회 — SCR-14 감사 로그 탭 (tb_audit_log, ADMIN 전용).

알려진 action 유형: REVEAL_AUTH / SETTLEMENT_CHANGE / REPORT_VIEW /
KAKAO_APPROVAL / CONFIG_CHANGE / DATA_EXPORT. 로그 적재는 각 도메인 라우터가 담당하며
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
from services.audit_logger import AuditLogger
from services.excel_export import (
    DAILY_EXPORT_LIMIT,
    MAX_EXPORT_ROWS,
    ColumnSpec,
    build_watermark,
    build_workbook,
    check_export_quota,
    enforce_row_limit,
    export_filename,
    xlsx_response,
)

router = APIRouter(prefix="/audit-logs", tags=["audit"])

# 내보내기 균형 보안(EX-5) — 상한/일일한도 상수·가드는 services.excel_export 공용부를 재사용한다.
# (이름을 모듈로 끌어와 endpoint별 monkeypatch·가독성 유지: DAILY_EXPORT_LIMIT·MAX_EXPORT_ROWS)


def _apply_filters(
    query,
    *,
    action: Optional[str],
    target_type: Optional[str],
    actor_id: Optional[str],
    date_from: Optional[date],
    date_to: Optional[date],
):
    """목록·내보내기 공유 필터 적용부('필터=파일' 보장 — 단일 진실원)."""
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
    return query


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
    query = _apply_filters(
        db.query(AuditLog),
        action=action,
        target_type=target_type,
        actor_id=actor_id,
        date_from=date_from,
        date_to=date_to,
    )

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


# 내보내기 컬럼 규격(EX-5) — 목록 화면 컬럼 + old/new(저장 redact값). 합계 없음.
_EXPORT_COLUMNS = [
    ColumnSpec("created_at", "시각", "date"),
    ColumnSpec("action", "액션", "text"),
    ColumnSpec("target_type", "대상유형", "text"),
    ColumnSpec("target_id", "대상", "text"),
    ColumnSpec("actor", "수행자", "text"),
    ColumnSpec("old_value", "이전값", "text"),
    ColumnSpec("new_value", "변경값", "text"),
]


def _export_filter_summary(n, action, target_type, actor_id, date_from, date_to):
    """감사 new_value — 행수 + 필터 요약(액션·대상·actor·기간)만(감사의 감사)."""
    parts = []
    if action:
        parts.append("action={0}".format(action))
    if target_type:
        parts.append("target_type={0}".format(target_type))
    if actor_id:
        parts.append("actor={0}".format(actor_id))
    if date_from:
        parts.append("from={0}".format(date_from))
    if date_to:
        parts.append("to={0}".format(date_to))
    return "rows={0}; filters={1}".format(n, ", ".join(parts) if parts else "none")


@router.get("/export")
def export_audit_logs(
    action: Optional[str] = Query(None, description="액션 필터"),
    target_type: Optional[str] = Query(None, description="대상 유형 필터"),
    actor_id: Optional[str] = Query(None, description="행위자 user_id 필터"),
    date_from: Optional[date] = Query(None, description="기간 시작"),
    date_to: Optional[date] = Query(None, description="기간 끝"),
    user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """감사 로그 엑셀 내보내기(EX-5, ADMIN) — 화면과 동일 필터의 '전체' 결과를 .xlsx로.

    목록과 동일한 ADMIN 게이트 + 행 상한(400)·일일 반출 횟수(429)·워터마크·DATA_EXPORT 감사.
    R2-E6: old_value·new_value는 **DB 저장값 그대로**(적재 시 이미 redact됨) 사용한다. 원문
    재조회·복호화 금지 — 감사값 자체가 유일 원천이므로 export가 비밀을 새로 노출할 수 없다.
    """
    # 일일 반출 횟수 제한 — 공용 가드(오늘 KST DATA_EXPORT 감사 건수 재사용)
    check_export_quota(db, user, daily_limit=DAILY_EXPORT_LIMIT)

    query = _apply_filters(
        db.query(AuditLog),
        action=action,
        target_type=target_type,
        actor_id=actor_id,
        date_from=date_from,
        date_to=date_to,
    )

    total = query.count()
    # 행 상한 — 공용 가드(무음 잘라내기 금지, 초과 시 400)
    enforce_row_limit(total, max_rows=MAX_EXPORT_ROWS)

    logs = query.order_by(AuditLog.created_at.desc()).all()
    unames = common.user_name_map(db, [log.actor_id for log in logs])
    rows = [
        {
            "created_at": log.created_at,
            "action": log.action,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "actor": unames.get(log.actor_id) or log.actor_id,
            # R2-E6: 저장된 redact값 그대로(원문 재조회·복호화 없음)
            "old_value": log.old_value,
            "new_value": log.new_value,
        }
        for log in logs
    ]

    content = build_workbook(
        _EXPORT_COLUMNS,
        rows,
        sheet_title="감사로그",
        watermark=build_watermark(user),
        total_row=None,  # 감사 로그는 합계 무의미
    )

    # 감사 — 감사 export 자체도 DATA_EXPORT 1건 기록(감사의 감사). 필터 요약만.
    AuditLogger.log_action(
        db,
        user.user_id,
        "DATA_EXPORT",
        target_type="AUDIT_LOG",
        new_value=_export_filter_summary(
            len(rows), action, target_type, actor_id, date_from, date_to
        ),
    )
    db.commit()

    return xlsx_response(content, export_filename("감사로그"))
