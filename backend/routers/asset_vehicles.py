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
from auth import get_current_user
from models import (
    Client,
    Project,
    ProjectSale,
    ProjectVehicle,
    PurchaseInvoice,
    User,
    get_db,
)
from routers import common
from services import accounting

router = APIRouter(prefix="/asset-vehicles", tags=["asset-vehicles"])

_REDUCTION_YEARS = tuple("reduction_y{0}".format(i) for i in range(1, 11))


def _num(value, digits):
    """Numeric(Decimal) → 반올림 float(None 안전)."""
    return round(float(value), digits) if value is not None else None


def _sum_opt(values):
    """None 안전 합 — 전부 None이면 None, 일부 None은 합에서 제외."""
    parts = [v for v in values if v is not None]
    return round(sum(parts), 2) if parts else None


def _project_accounting(db: Session, project_ids):
    """distinct 사업별 회계 집계(compute_accounting 재사용) — 사업당 1회, N+1 회피.

    projects.py 상세 경로와 동일 입력(제품=Σ매입, 예상지급액=Σ차량 expected_payout,
    거래계약 목록, 승인상태)을 **배치 조회**로 모아 사업별로 1회 계산한다.
    반환: {project_id: {"revenue": sale_recognized, "cost": product, "profit": gross_profit}}
    """
    ids = list(project_ids)
    if not ids:
        return {}
    # 제품(총매입) Σ — 사업별(부록 L.3, 없으면 0)
    products = dict(
        db.query(PurchaseInvoice.project_id, func.sum(PurchaseInvoice.amount))
        .filter(PurchaseInvoice.project_id.in_(ids))
        .group_by(PurchaseInvoice.project_id)
        .all()
    )
    # 예상지급액 Σ(차량 expected_payout) — 사업 전체 차량 기준. 전건 None이면 SUM→None 전파
    payouts = dict(
        db.query(ProjectVehicle.project_id, func.sum(ProjectVehicle.expected_payout))
        .filter(ProjectVehicle.project_id.in_(ids))
        .group_by(ProjectVehicle.project_id)
        .all()
    )
    # 승인상태 — 사업 마스터
    approvals = dict(
        db.query(Project.project_id, Project.approval_status)
        .filter(Project.project_id.in_(ids))
        .all()
    )
    # 거래계약 — 사업별 목록으로 묶기
    sales_by_pid = {pid: [] for pid in ids}
    for s in db.query(ProjectSale).filter(ProjectSale.project_id.in_(ids)).all():
        sales_by_pid.setdefault(s.project_id, []).append(s)

    result = {}
    for pid in ids:
        payout = payouts.get(pid)
        product = products.get(pid)
        acct = accounting.compute_accounting(
            approval_status=approvals.get(pid),
            product=round(float(product), 2) if product is not None else 0.0,
            expected_payment=round(float(payout), 2) if payout is not None else None,
            sales=sales_by_pid.get(pid, []),
        )
        result[pid] = {
            "revenue": acct["sale_recognized"],
            "cost": acct["product"],
            "profit": acct["gross_profit"],
        }
    return result


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
    q = (
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

    total = q.count()
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
    )

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
            project_status=project_status,
            approval_status=proj_approval,
            # 행별 사업 회계값 — page 프로젝트는 distinct 집합의 부분이므로 위 dict에서 조회(D1-A)
            project_revenue=acct_by_pid.get(v.project_id, {}).get("revenue"),
            project_cost=acct_by_pid.get(v.project_id, {}).get("cost"),
            **{f: _num(getattr(v, f), 3) for f in _REDUCTION_YEARS},
        )
        for v, project_name, approved_at, proj_approval, project_status, company_name in rows
    ]
    return schemas.AssetVehicleListResponse(items=items, total=total, kpi=kpi)
