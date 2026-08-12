"""통합 현황판 — SCR-01 (P1).

- KPI: 관리 고객사(+증감) / 당월 보고서 발송 n/m / 미처리 긴급 이슈 /
  계약 검토·협의 중(HOLD)
- 최근 활동 타임라인 20건 + 미처리 이슈 목록
- 이달 보고서 진행 위젯은 GET /reports 의 summary 를 프론트에서 재사용 (별도 집계 없음)
"""

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user
from models import (
    ActivityHistory,
    Client,
    ReportDelivery,
    User,
    get_db,
)
from routers import common

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=schemas.DashboardStats)
def dashboard_stats(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """통합 현황판 데이터 일괄 조회."""
    period = common.current_period()
    month_start, month_end = common.period_bounds(period)
    # created_at은 naive UTC 저장 — KST 라벨 월 경계를 UTC로 환산해 비교(월초 9시간 편차 방지)
    utc_month_start = month_start - timedelta(hours=9)
    utc_month_end = month_end - timedelta(hours=9)

    # --- KPI ---
    total_clients = db.query(Client).filter(Client.contract_status == "ACTIVE").count()
    client_delta = (
        db.query(Client)
        .filter(Client.created_at >= utc_month_start, Client.created_at <= utc_month_end)
        .count()
    )
    report_target = (
        db.query(ReportDelivery)
        .filter(ReportDelivery.period == period, ReportDelivery.status != "CANCELED")
        .count()
    )
    report_sent = (
        db.query(ReportDelivery)
        .filter(
            ReportDelivery.period == period,
            ReportDelivery.status.in_(["SENT", "CONFIRMED"]),
        )
        .count()
    )
    urgent_open_issues = (
        db.query(ActivityHistory)
        .filter(
            ActivityHistory.activity_type == "ISSUE",
            ActivityHistory.priority == "URGENT",
            ActivityHistory.issue_status != "CLOSED",
        )
        .count()
    )
    contract_hold_clients = db.query(Client).filter(Client.contract_status == "HOLD").count()

    # --- 최근 활동 타임라인 20건 (전사, 작성자 표기) ---
    recent = (
        db.query(ActivityHistory)
        .order_by(ActivityHistory.activity_date.desc(), ActivityHistory.created_at.desc())
        .limit(20)
        .all()
    )

    # --- 미처리 이슈 (긴급 우선 → 마감일순) ---
    open_issues = (
        db.query(ActivityHistory)
        .filter(
            ActivityHistory.activity_type == "ISSUE",
            ActivityHistory.issue_status != "CLOSED",
        )
        .order_by(
            case((ActivityHistory.priority == "URGENT", 0), else_=1).asc(),
            ActivityHistory.due_date.asc(),
            ActivityHistory.activity_date.desc(),
        )
        .all()
    )

    return schemas.DashboardStats(
        period=period,
        kpi=schemas.DashboardKpi(
            total_clients=total_clients,
            client_delta=client_delta,
            report_target=report_target,
            report_sent=report_sent,
            urgent_open_issues=urgent_open_issues,
            contract_hold_clients=contract_hold_clients,
        ),
        recent_activities=common.build_history_outs(db, recent),
        open_issues=common.build_history_outs(db, open_issues),
    )
