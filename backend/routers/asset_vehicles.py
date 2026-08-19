"""자산관리 > 전기버스 — 크로스-프로젝트 차량 뷰 (AV-1, 내부 전용 조회).

여러 감축사업을 가로질러 참여 차량(tb_project_vehicle)을 한 목록으로 나열한다.
project-scoped `GET /projects/{id}/vehicles`(선례)와 동일한 필터·통합검색·페이지네이션·
합계 관용구를 따르되, project_id 고정 없이 전 프로젝트를 대상으로 한다.
조회 전용(신규 컬럼 없음) — 재무 KPI는 AV-2 증분에서 확장한다.

의존성은 get_current_user 하나 — 외부역할(PARTNER/INVESTOR)은 이 지점에서 자동 403(포털 격리).
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_role
from models import (
    Client,
    Project,
    ProjectSale,
    ProjectVehicle,
    User,
    get_db,
)
from routers import common
from services import finance_query
from services.audit_logger import AuditLogger
from services.market_rate import expected_revenue, trailing_avg_rate
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

router = APIRouter(prefix="/asset-vehicles", tags=["asset-vehicles"])

# 내보내기 균형 보안(EX-4) — 상한/일일한도 상수·가드는 services.excel_export 공용부를 재사용한다.
# (이름을 모듈로 끌어와 endpoint별 monkeypatch·가독성 유지: DAILY_EXPORT_LIMIT·MAX_EXPORT_ROWS)

_REDUCTION_YEARS = tuple("reduction_y{0}".format(i) for i in range(1, 11))


def _num(value, digits):
    """Numeric(Decimal) → 반올림 float(None 안전)."""
    return round(float(value), digits) if value is not None else None


def _sum_opt(values):
    """None 안전 합 — 전부 None이면 None, 일부 None은 합에서 제외."""
    parts = [v for v in values if v is not None]
    return round(sum(parts), 2) if parts else None


def _project_accounting(db: Session, project_ids):
    """distinct 사업별 회계 집계 — 공용 배치 헬퍼(finance_query) 위에 차량 뷰 키만 매핑.

    산식·쿼리는 project_accounting_batch(단일 진실원)에 위임하고, 이 뷰가 쓰는
    revenue/cost/profit 3키(sale_recognized·product·gross_profit)만 골라 반환한다.
    반환: {project_id: {"revenue": sale_recognized, "cost": product, "profit": gross_profit}}
    """
    acct_by_pid = finance_query.project_accounting_batch(db, project_ids)
    return {
        pid: {
            "revenue": acct["sale_recognized"],
            "cost": acct["product"],
            "profit": acct["gross_profit"],
        }
        for pid, acct in acct_by_pid.items()
    }


def _base_query(db: Session):
    """차량 뷰 base 쿼리 — Project(inner)·Client(outer) 조인. 목록·내보내기 공유."""
    return (
        db.query(
            ProjectVehicle,
            Project.project_name,
            Project.approved_at,
            Project.approval_status,
            Project.project_status,
            Client.company_name,
        )
        .join(Project, ProjectVehicle.project_id == Project.project_id)
        .outerjoin(Client, ProjectVehicle.client_id == Client.client_id)
    )


def _apply_filters(
    q,
    db: Session,
    *,
    project_id: Optional[str],
    region: Optional[str],
    client_id: Optional[str],
    approval_status: Optional[str],
    buyer_id: Optional[str],
    registered_from: Optional[date],
    registered_to: Optional[date],
    expire_before: Optional[date],
    search: Optional[str],
):
    """목록·내보내기 공유 필터 적용부('필터=파일' 보장 — 단일 진실원)."""
    if project_id:
        q = q.filter(ProjectVehicle.project_id == project_id)
    if region:
        q = q.filter(ProjectVehicle.region == region)
    if client_id == "__none__":
        q = q.filter(ProjectVehicle.client_id.is_(None))  # 미지정 운수사
    elif client_id:
        q = q.filter(ProjectVehicle.client_id == client_id)
    if approval_status:
        q = q.filter(Project.approval_status == approval_status)
    if buyer_id:
        # 해당 매수자와 거래계약이 있는 사업의 차량으로 한정(부록 N.8)
        q = q.filter(
            ProjectVehicle.project_id.in_(
                db.query(ProjectSale.project_id).filter(ProjectSale.buyer_id == buyer_id)
            )
        )
    if registered_from:
        q = q.filter(ProjectVehicle.registered_at >= registered_from)
    if registered_to:
        q = q.filter(ProjectVehicle.registered_at <= registered_to)
    if expire_before:
        # 차령만료 임박 — 만료일 NULL은 자동 제외(NULL 비교)
        q = q.filter(ProjectVehicle.expire_at <= expire_before)
    if search and search.strip():
        kw = "%{0}%".format(common.escape_like(search.strip()))
        client_ids = [
            c[0]
            for c in db.query(Client.client_id).filter(
                Client.company_name.ilike(kw, escape="\\")
            )
        ]
        conds = [ProjectVehicle.vehicle_no.ilike(kw, escape="\\")]
        if client_ids:
            conds.append(ProjectVehicle.client_id.in_(client_ids))
        q = q.filter(or_(*conds))
    return q


def _build_kpi(db: Session, q, avg6=None):
    """차량 KPI(필터 결과 전체 합) + 재무 KPI(distinct 사업 회계 합) — 목록·내보내기 공유.

    반환: (AssetVehicleKpi, {project_id: {revenue,cost,profit}}). 후자는 행별 사업값 조회에 재사용.
    예상수익 KPI는 전체 집계 grain(Σeff × 6개월평균시세) — 가시 페이지 아닌 필터 전체
    합이므로 예상지급액 KPI와 동일하게 가시행 합과 불일치가 정상이다.
    """
    # 차량 KPI — 페이지네이션 전 필터 결과 전체 합(None 안전)
    agg = q.with_entities(
        func.count(ProjectVehicle.vehicle_id),
        func.sum(ProjectVehicle.total_reduction),
        func.sum(ProjectVehicle.effective_reduction),
        func.sum(ProjectVehicle.expected_payout),
    ).one()
    # 재무 KPI — 필터에 걸린 distinct 사업 전체의 회계 합(부분집합 과대계상 방지, D2)
    distinct_pids = [
        r[0] for r in q.with_entities(ProjectVehicle.project_id).distinct().all()
    ]
    acct_by_pid = _project_accounting(db, distinct_pids)
    kpi = schemas.AssetVehicleKpi(
        vehicle_count=agg[0] or 0,
        total_reduction=_num(agg[1], 3),
        effective_reduction_sum=_num(agg[2], 3),
        expected_payout_sum=_num(agg[3], 2),
        revenue=_sum_opt(a["revenue"] for a in acct_by_pid.values()),
        cost=_sum_opt(a["cost"] for a in acct_by_pid.values()),
        profit=_sum_opt(a["profit"] for a in acct_by_pid.values()),
        # 예상수익 — 전체 Σ잔여반영감축량 × 6개월평균시세(원단위 절사, None 안전)
        expected_revenue=expected_revenue(agg[2], avg6),
    )
    return kpi, acct_by_pid


@router.get("", response_model=schemas.AssetVehicleListResponse)
def list_asset_vehicles(
    project_id: Optional[str] = Query(None, description="사업 필터"),
    region: Optional[str] = Query(None, description="지역 필터"),
    client_id: Optional[str] = Query(None, description="운수사 필터(__none__=미지정)"),
    approval_status: Optional[str] = Query(None, description="승인상태 필터(Project)"),
    buyer_id: Optional[str] = Query(None, description="매수자 필터(거래계약 보유 사업의 차량)"),
    registered_from: Optional[date] = Query(None, description="차량등록일 시작(이상)"),
    registered_to: Optional[date] = Query(None, description="차량등록일 끝(이하)"),
    expire_before: Optional[date] = Query(None, description="차령만료 임박(만료일 이하)"),
    search: Optional[str] = Query(None, description="차량번호·운수사명 검색"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """크로스-프로젝트 차량 목록(필터·통합검색·페이지) + 차량 KPI(필터 결과 전체 합)."""
    q = _apply_filters(
        _base_query(db),
        db,
        project_id=project_id,
        region=region,
        client_id=client_id,
        approval_status=approval_status,
        buyer_id=buyer_id,
        registered_from=registered_from,
        registered_to=registered_to,
        expire_before=expire_before,
        search=search,
    )

    total = q.count()
    avg6 = trailing_avg_rate(db)
    kpi, acct_by_pid = _build_kpi(db, q, avg6)

    rows = (
        # 정렬 — 사업명·차량번호. vehicle_id 타이브레이커로 페이지 경계 누락/중복 방지
        q.order_by(
            Project.project_name.asc(),
            ProjectVehicle.vehicle_no.asc(),
            ProjectVehicle.vehicle_id.asc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        schemas.AssetVehicleRow(
            vehicle_id=v.vehicle_id,
            project_id=v.project_id,
            project_name=project_name,
            vehicle_no=v.vehicle_no,
            region=v.region,
            client_id=v.client_id,
            client_name=company_name,
            registered_at=v.registered_at,
            expire_at=v.expire_at,
            approved_at=approved_at,
            total_reduction=_num(v.total_reduction, 3),
            remaining_age=_num(v.remaining_age, 3),
            effective_reduction=_num(v.effective_reduction, 3),
            expected_payout=_num(v.expected_payout, 2),
            # 예상수익 — 차량 leaf(effective_reduction × 6개월평균시세, 원단위 절사, None 안전)
            expected_revenue=expected_revenue(v.effective_reduction, avg6),
            project_status=project_status,
            approval_status=proj_approval,
            # 행별 사업 회계값 — page 프로젝트는 distinct 집합의 부분이므로 위 dict에서 조회(D1-A)
            project_revenue=acct_by_pid.get(v.project_id, {}).get("revenue"),
            project_cost=acct_by_pid.get(v.project_id, {}).get("cost"),
            **{f: _num(getattr(v, f), 3) for f in _REDUCTION_YEARS},
        )
        for v, project_name, approved_at, proj_approval, project_status, company_name in rows
    ]
    return schemas.AssetVehicleListResponse(
        items=items,
        total=total,
        kpi=kpi,
        market_rate_avg6=float(avg6) if avg6 is not None else None,
    )


# 내보내기 컬럼 규격(EX-4) — 화면 컬럼과 정합(프로젝트명 … 원가(사업))
_EXPORT_COLUMNS = [
    ColumnSpec("project_name", "프로젝트명", "text"),
    ColumnSpec("vehicle_no", "차량번호", "text"),
    ColumnSpec("region", "지역", "text"),
    ColumnSpec("client_name", "운수사", "text"),
    ColumnSpec("registered_at", "차량등록일", "date"),
    ColumnSpec("expire_at", "차령만료일", "date"),
    ColumnSpec("approved_at", "사업승인일", "date"),
    ColumnSpec("total_reduction", "10년 총감축량", "number"),
    ColumnSpec("remaining_age", "잔여차령", "number"),
    ColumnSpec("effective_reduction", "잔여반영감축량", "number"),
    ColumnSpec("expected_payout", "예상지급액", "money"),
    ColumnSpec("expected_revenue", "예상수익", "money"),
    ColumnSpec("project_revenue", "매출(사업)", "money"),
    ColumnSpec("project_cost", "원가(사업)", "money"),
]


def _export_filter_summary(
    n,
    project_id,
    region,
    client_id,
    approval_status,
    buyer_id,
    registered_from,
    registered_to,
    expire_before,
    search,
):
    """감사 new_value — 행수 + 필터 요약(id·지역·상태·기간)만. 금액·비밀값 원문 미기록(R2-E6)."""
    parts = []
    if project_id:
        parts.append("project={0}".format(project_id))
    if region:
        parts.append("region={0}".format(region))
    if client_id:
        parts.append("client={0}".format(client_id))
    if approval_status:
        parts.append("approval={0}".format(approval_status))
    if buyer_id:
        parts.append("buyer={0}".format(buyer_id))
    if registered_from:
        parts.append("reg_from={0}".format(registered_from))
    if registered_to:
        parts.append("reg_to={0}".format(registered_to))
    if expire_before:
        parts.append("expire_before={0}".format(expire_before))
    if search and search.strip():
        parts.append("search={0}".format(search.strip()))
    return "rows={0}; filters={1}".format(n, ", ".join(parts) if parts else "none")


@router.get("/export")
def export_asset_vehicles(
    project_id: Optional[str] = Query(None, description="사업 필터"),
    region: Optional[str] = Query(None, description="지역 필터"),
    client_id: Optional[str] = Query(None, description="운수사 필터(__none__=미지정)"),
    approval_status: Optional[str] = Query(None, description="승인상태 필터(Project)"),
    buyer_id: Optional[str] = Query(None, description="매수자 필터(거래계약 보유 사업의 차량)"),
    registered_from: Optional[date] = Query(None, description="차량등록일 시작(이상)"),
    registered_to: Optional[date] = Query(None, description="차량등록일 끝(이하)"),
    expire_before: Optional[date] = Query(None, description="차령만료 임박(만료일 이하)"),
    search: Optional[str] = Query(None, description="차량번호·운수사명 검색"),
    user: User = Depends(require_role("MANAGER")),
    db: Session = Depends(get_db),
):
    """전기버스 자산 엑셀 내보내기(EX-4) — 화면과 동일 필터의 '전체' 결과를 .xlsx로.

    조회(목록)보다 좁은 MANAGER 게이트 + 행 상한(400)·일일 반출 횟수(429)·워터마크·
    DATA_EXPORT 감사(금액 원문 미기록)로 대량 유출을 억제한다. 페이지네이션 없음(전체행).
    """
    # 일일 반출 횟수 제한 — 공용 가드(오늘 KST DATA_EXPORT 감사 건수 재사용)
    check_export_quota(db, user, daily_limit=DAILY_EXPORT_LIMIT)

    q = _apply_filters(
        _base_query(db),
        db,
        project_id=project_id,
        region=region,
        client_id=client_id,
        approval_status=approval_status,
        buyer_id=buyer_id,
        registered_from=registered_from,
        registered_to=registered_to,
        expire_before=expire_before,
        search=search,
    )

    total = q.count()
    # 행 상한 — 공용 가드(무음 잘라내기 금지, 초과 시 400)
    enforce_row_limit(total, max_rows=MAX_EXPORT_ROWS)

    avg6 = trailing_avg_rate(db)
    kpi, acct_by_pid = _build_kpi(db, q, avg6)

    # 전체 차량 행(목록과 동일 정렬, 페이지네이션 없음)
    projects = q.order_by(
        Project.project_name.asc(),
        ProjectVehicle.vehicle_no.asc(),
        ProjectVehicle.vehicle_id.asc(),
    ).all()
    rows = []
    for v, project_name, approved_at, _proj_approval, _project_status, company_name in projects:
        acct = acct_by_pid.get(v.project_id, {})
        rows.append(
            {
                "project_name": project_name,
                "vehicle_no": v.vehicle_no,
                "region": v.region,
                "client_name": company_name,
                "registered_at": v.registered_at,
                "expire_at": v.expire_at,
                "approved_at": approved_at,
                "total_reduction": _num(v.total_reduction, 3),
                "remaining_age": _num(v.remaining_age, 3),
                "effective_reduction": _num(v.effective_reduction, 3),
                "expected_payout": _num(v.expected_payout, 2),
                "expected_revenue": expected_revenue(v.effective_reduction, avg6),
                "project_revenue": acct.get("revenue"),
                "project_cost": acct.get("cost"),
            }
        )

    # 합계행 = KPI 합(차량 감축·예상지급 + 재무 매출/원가). 차량수는 데이터 행수와 동일.
    total_row = {
        "total_reduction": kpi.total_reduction,
        "effective_reduction": kpi.effective_reduction_sum,
        "expected_payout": kpi.expected_payout_sum,
        "expected_revenue": kpi.expected_revenue,
        "project_revenue": kpi.revenue,
        "project_cost": kpi.cost,
    }

    content = build_workbook(
        _EXPORT_COLUMNS,
        rows,
        sheet_title="전기버스자산",
        watermark=build_watermark(user),
        total_row=total_row,
    )

    # 감사 — 반환 직전 기록(행수·필터 요약만, 금액·비밀값 원문 미기록) 후 커밋
    AuditLogger.log_action(
        db,
        user.user_id,
        "DATA_EXPORT",
        target_type="ASSET_VEHICLES",
        new_value=_export_filter_summary(
            len(rows),
            project_id,
            region,
            client_id,
            approval_status,
            buyer_id,
            registered_from,
            registered_to,
            expire_before,
            search,
        ),
    )
    db.commit()

    return xlsx_response(content, export_filename("전기버스자산"))
