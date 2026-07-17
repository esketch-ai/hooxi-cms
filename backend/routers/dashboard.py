"""통합 현황판 — SCR-01 (P1).

- KPI 5: 관리 고객사(+증감) / 당월 보고서 발송 n/m / 미처리 긴급 이슈 /
  계약 검토·협의 중(HOLD) / 당월 예상 청구액 🔒
- 리텐션 퍼널: §10.2 기본 매핑 — tb_config `funnel_mapping` 오버라이드 존중
- 최근 활동 타임라인 20건 + 미처리 이슈 목록
"""

import json
from datetime import timedelta
from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import case
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user
from models import (
    ActivityHistory,
    Client,
    Config,
    Project,
    ProjectClientMap,
    ReportDelivery,
    User,
    get_db,
)
from routers import common
from routers.settlements import _period_of  # 정산 기준월 정의 재사용 (SCR-07과 동일)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# §10.2 기본 매핑 — 리텐션 8단계 → 퍼널 4단계
_DEFAULT_FUNNEL_MAPPING = {
    "관심/접촉": ["인지", "관심"],
    "제안/검토": ["검토"],
    "계약 진행": ["구매결정"],
    "온보딩/활성": ["온보딩", "활용", "재계약", "확장"],
}


def _funnel_mapping(db: Session) -> Dict[str, List[str]]:
    """tb_config `funnel_mapping`(JSON) 오버라이드 존중 — 파싱 실패 시 기본값."""
    config = db.get(Config, "funnel_mapping")
    if config and config.config_value:
        try:
            parsed = json.loads(config.config_value)
            if isinstance(parsed, dict) and all(isinstance(v, list) for v in parsed.values()):
                return parsed
        except (ValueError, TypeError):
            pass
    return _DEFAULT_FUNNEL_MAPPING


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

    # 당월 예상 청구액 🔒 — 미완료(대기·청구) 정산 매핑 중 **당월분만** 합산.
    # 기준월 정의는 정산 화면(SCR-07)과 동일: _period_of(billed_at 우선, 미청구는 예상 발급월)
    # → 정산 화면의 당월 필터 합계와 항상 일치. 당월 산출분 없으면 None(미정).
    billing_maps = (
        db.query(ProjectClientMap)
        .filter(ProjectClientMap.settlement_status.in_(["STANDBY", "BILLED"]))
        .all()
    )
    billing_projects = {
        p.project_id: p
        for p in db.query(Project)
        .filter(Project.project_id.in_({m.project_id for m in billing_maps}))
        .all()
    } if billing_maps else {}
    monthly_amounts = [
        float(m.expected_amount)
        for m in billing_maps
        if m.expected_amount is not None
        and _period_of(m, billing_projects.get(m.project_id)) == period
    ]
    expected_billing_amount = sum(monthly_amounts) if monthly_amounts else None

    # --- 리텐션 퍼널: 고객사별 최신 retention_stage → 4단계 집계 ---
    mapping = _funnel_mapping(db)
    stage_rows = (
        db.query(ActivityHistory.client_id, ActivityHistory.retention_stage, ActivityHistory.activity_date)
        .filter(ActivityHistory.retention_stage.isnot(None), ActivityHistory.client_id.isnot(None))
        .order_by(ActivityHistory.activity_date.asc())
        .all()
    )
    latest_stage = {}  # 시간순 순회 → 마지막 값이 최신
    for client_id, stage, _dt in stage_rows:
        latest_stage[client_id] = stage
    funnel = []
    for funnel_stage, retention_stages in mapping.items():
        count = sum(1 for s in latest_stage.values() if s in retention_stages)
        funnel.append(schemas.FunnelStage(stage=funnel_stage, count=count))

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
            expected_billing_amount=expected_billing_amount,
        ),
        funnel=funnel,
        recent_activities=common.build_history_outs(db, recent),
        open_issues=common.build_history_outs(db, open_issues),
    )
