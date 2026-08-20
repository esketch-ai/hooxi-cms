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
            if m and m.contract_status == "DONE":
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


# 지역(조합) 표시 순서 — 현황 엑셀 관례. 목록 밖 지역은 뒤에 가나다 순 부착.
_REGION_ORDER = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "경기", "강원",
    "충북", "충남", "전북", "전남", "경북", "경남", "제주", "세종",
]


@router.get("/fleet-tables", response_model=schemas.DashboardFleetTables)
def dashboard_fleet_tables(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """운수사 지역별 통계표(F6) — 현황 탭 6표 재현(최신 월 대수 + 수작업 분류).

    대수 기준 3표(전체/외부사업 대상(할당·목표 제외)/외부사업 미계약) +
    업체수 기준 3표(전체/규제·비규제/외부사업 대상). 분류는 tb_fleet_mgmt(현황 탭 자동 반영).
    """
    period = db.query(func.max(FleetStatus.period)).scalar()
    if not period:
        return schemas.DashboardFleetTables()

    rows = (
        db.query(
            FleetStatus.region,
            FleetStatus.license_count,
            FleetStatus.electric,
            FleetStatus.hydrogen,
            FleetMgmt.target_type,
            FleetMgmt.contract_status,
            FleetMgmt.regulated_type,
        )
        .outerjoin(FleetMgmt, FleetMgmt.client_id == FleetStatus.client_id)
        .filter(FleetStatus.period == period)
        .all()
    )

    def _blank():
        return {"c1": 0, "c2": 0, "c3": 0}

    # 6개 표의 지역별 누적기 — {region: {c1,c2,c3}}
    acc = {k: {} for k in ("T1", "T2", "T3", "T4", "T5", "T6")}

    def _add(tkey, region, c1=0, c2=0, c3=0):
        d = acc[tkey].setdefault(region or "미상", _blank())
        d["c1"] += c1
        d["c2"] += c2
        d["c3"] += c3

    for region, lic, ev, h2, target, contract, regulated in rows:
        lic = int(lic or 0)
        ev = int(ev or 0)
        h2 = int(h2 or 0)
        is_biz = target == "BIZ"
        is_reg = target == "REG"
        # 외부사업 대상 = 사업대상 & 규제여부(할당/목표) 제외
        ext = is_biz and regulated not in ("ALLOC", "GOAL")
        done = contract == "DONE"
        none = contract == "NONE"

        # 대수 기준
        _add("T1", region, lic, ev, h2)  # 전체 현황
        if ext:
            _add("T2", region, lic, ev, h2)  # 외부사업 대상(할당/목표 제외)
            if none:
                _add("T3", region, lic, ev, h2)  # 외부사업 미계약
        # 업체수 기준
        _add("T4", region, 1, 1 if done else 0, 1 if none else 0)  # 전체: 전체/계약완료/미계약
        _add("T5", region, 1, 1 if is_reg else 0, 1 if is_biz else 0)  # 규제/비규제
        if is_biz:
            _add("T6", region, 1, 1 if done else 0, 1 if none else 0)  # 외부사업: 소계/계약/미계약

    def _sorted_regions(regmap):
        present = list(regmap.keys())
        present.sort(key=lambda r: (_REGION_ORDER.index(r) if r in _REGION_ORDER else 999, r))
        return present

    def _build(tkey, title, basis, columns):
        regmap = acc[tkey]
        total = _blank()
        rowlist = []
        for r in _sorted_regions(regmap):
            d = regmap[r]
            rowlist.append(schemas.FleetTableRow(region=r, c1=d["c1"], c2=d["c2"], c3=d["c3"]))
            for k in ("c1", "c2", "c3"):
                total[k] += d[k]
        return schemas.FleetTable(
            key=tkey, title=title, basis=basis, columns=columns,
            total=schemas.FleetTableRow(region="전국", **total), rows=rowlist,
        )

    tables = [
        _build("T1", "전체 현황", "license", ["면허대수", "전기", "수소"]),
        _build("T2", "외부사업 대상 (할당/목표 제외)", "license", ["면허대수", "전기", "수소"]),
        _build("T3", "외부사업 미계약 현황", "license", ["면허대수", "전기", "수소"]),
        _build("T4", "전체 현황 (업체수)", "count", ["전체", "계약완료", "미계약"]),
        _build("T5", "규제/비규제 구분", "count", ["소계", "규제", "외부사업"]),
        _build("T6", "외부사업 대상 (업체수)", "count", ["소계", "계약", "미계약"]),
    ]
    return schemas.DashboardFleetTables(period=period, tables=tables)
