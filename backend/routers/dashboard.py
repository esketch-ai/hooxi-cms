"""통합 현황판 — SCR-01 (P1).

- KPI: 관리 고객사(+증감) / 당월 보고서 발송 n/m / 미처리 긴급 이슈 /
  계약 검토·협의 중(HOLD)
- 최근 활동 타임라인 20건 + 미처리 이슈 목록
- 이달 보고서 진행 위젯은 GET /reports 의 summary 를 프론트에서 재사용 (별도 집계 없음)
"""

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user
from models import (
    ActivityHistory,
    Client,
    FleetMgmt,
    FleetStatus,
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


@router.get("/fleet", response_model=schemas.DashboardFleet)
def dashboard_fleet(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """운수사 계약대수 현황 섹션 — 데이터 있는 최신 월 집계 + 전월 대비 전기 증감."""
    period = db.query(func.max(FleetStatus.period)).scalar()
    if not period:
        return schemas.DashboardFleet()

    def _sum(col, per):
        return db.query(func.coalesce(func.sum(col), 0)).filter(
            FleetStatus.period == per
        ).scalar() or 0

    companies = db.query(FleetStatus).filter(FleetStatus.period == period).count()
    matched = (
        db.query(FleetStatus)
        .filter(FleetStatus.period == period, FleetStatus.client_id.isnot(None))
        .count()
    )
    total_license = _sum(FleetStatus.license_count, period)
    total_count = _sum(FleetStatus.total_count, period)
    total_ev = _sum(FleetStatus.electric, period)
    ev_share = round(total_ev / total_count * 100, 1) if total_count else 0.0

    # 전월(직전 존재 월) 대비 전기 증감
    prev_period = (
        db.query(func.max(FleetStatus.period))
        .filter(FleetStatus.period < period)
        .scalar()
    )
    ev_delta = total_ev - (_sum(FleetStatus.electric, prev_period) if prev_period else 0)

    # 업종·지역 분포(면허·전기)
    def _dist(group_col):
        rows = (
            db.query(
                group_col,
                func.coalesce(func.sum(FleetStatus.license_count), 0),
                func.coalesce(func.sum(FleetStatus.electric), 0),
            )
            .filter(FleetStatus.period == period)
            .group_by(group_col)
            .all()
        )
        return [
            schemas.FleetDistItem(key=(k or "미상"), license=int(lic), electric=int(ev))
            for k, lic, ev in rows
        ]

    # 대상여부·계약여부 — 최신 월에 데이터가 있는 고객사의 수작업 관리 집계
    client_ids = [
        r[0]
        for r in db.query(FleetStatus.client_id)
        .filter(FleetStatus.period == period, FleetStatus.client_id.isnot(None))
        .distinct()
        .all()
    ]
    biz_target = reg_target = contracted = uncontracted = 0
    if client_ids:
        mgmts = db.query(FleetMgmt).filter(FleetMgmt.client_id.in_(client_ids)).all()
        by_cid = {m.client_id: m for m in mgmts}
        for cid in client_ids:
            m = by_cid.get(cid)
            if m and m.target_type == "BIZ":
                biz_target += 1
            elif m and m.target_type == "REG":
                reg_target += 1
            if m and m.contract_yn == "Y":
                contracted += 1
            else:
                uncontracted += 1

    return schemas.DashboardFleet(
        period=period,
        prev_period=prev_period,
        companies=companies,
        matched_companies=matched,
        total_license=int(total_license),
        total_count=int(total_count),
        total_electric=int(total_ev),
        ev_share=ev_share,
        ev_delta=int(ev_delta),
        biz_target=biz_target,
        reg_target=reg_target,
        contracted=contracted,
        uncontracted=uncontracted,
        by_industry=_dist(FleetStatus.industry),
        by_region=_dist(FleetStatus.region),
    )
