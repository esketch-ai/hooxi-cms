"""감축 사업 관리 — SCR-06 (P2).

- 목록: FilterBar(진행 상태·담당 PM·모니터링 주기) + 예상 발급일(D-day용)
- 상세: 개요 + 진행 단계 + 참여 차량·운수사·거래계약·회계 원장층 파생
"""

import calendar
import math
from datetime import date, timedelta
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from services import excel_import
from models import (
    Asset,
    Buyer,
    Client,
    ClientVehicle,
    Code,
    Project,
    ProjectSale,
    ProjectStage,
    ProjectVehicle,
    PurchaseInvoice,
    User,
    get_db,
)
from routers import common
from routers.codes import validate_active_code
from services import accounting
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/projects", tags=["projects"])

_PROJECT_FIELDS = [
    "client_id", "project_name", "reg_code", "project_status",
    "reg_date", "credit_start_date", "credit_end_date", "credit_period_type",
    "mon_start_date", "mon_end_date", "mon_cycle",
    "expected_issue_date", "expected_credits",
    "issued_credits", "issued_at", "manager_id", "approval_status",
]  # 지급 파라미터(max_payment·approved_at 등)는 payout-params 전용 경로만(차량 재계산 동반)


def _project_status_codes(db: Session):
    """PROJECT_STATUS 활성 코드를 sort_order 순으로 — 단계 시드/정렬 소스(하드코딩 금지)."""
    rows = (
        db.query(Code)
        .filter(Code.category == "PROJECT_STATUS", Code.active == "Y")
        .all()
    )
    rows.sort(key=lambda r: (r.sort_order if r.sort_order is not None else 999, r.code))
    return [(r.code, r.sort_order) for r in rows]


def _seed_stages(db: Session, project: Project) -> None:
    """프로젝트 진행 단계 행을 PROJECT_STATUS 코드별로 보강(멱등). 커밋은 호출부 책임.

    신규 프로젝트·기존(레거시) 프로젝트 모두에서 누락 단계만 추가한다."""
    existing = {
        s.stage_code
        for s in db.query(ProjectStage).filter(
            ProjectStage.project_id == project.project_id
        )
    }
    for code, sort_order in _project_status_codes(db):
        if code not in existing:
            db.add(
                ProjectStage(
                    project_id=project.project_id,
                    stage_code=code,
                    sort_order=sort_order,
                )
            )


def _stage_outs(db: Session, project: Project):
    """진행 단계 목록(정렬) + 지연 단계 수. 지연 = 예정 경과 & 미도달(실제일 없음)."""
    today = date.today()
    rows = list(
        db.query(ProjectStage).filter(ProjectStage.project_id == project.project_id)
    )
    rows.sort(
        key=lambda s: (s.sort_order if s.sort_order is not None else 999, s.stage_code)
    )
    outs, delayed = [], 0
    for s in rows:
        is_delayed = bool(
            s.planned_date and s.actual_date is None and s.planned_date < today
        )
        if is_delayed:
            delayed += 1
        out = schemas.ProjectStageOut.model_validate(s, from_attributes=True)
        outs.append(out.model_copy(update={"delayed": is_delayed}))
    return outs, delayed


_REDUCTION_YEARS = tuple("reduction_y{0}".format(i) for i in range(1, 11))
_VEHICLE_FIELDS = (
    "client_id", "asset_id", "vehicle_no", "region", "introduction_type",
    "registered_at", *_REDUCTION_YEARS, "private_invest_ratio", "memo",
)


def _sum_reductions(obj) -> Optional[float]:
    """연차(1~10) 감축량 합 — 값이 하나도 없으면 None(미입력)."""
    nums = [float(getattr(obj, f)) for f in _REDUCTION_YEARS if getattr(obj, f) is not None]
    return round(sum(nums), 3) if nums else None


def _link_client_vehicle(db: Session, vehicle: ProjectVehicle) -> None:
    """참여 차량의 fleet 마스터 링크 신선도 — vehicle_no 일치 ClientVehicle을 찾아 세팅(부록 M).

    client_vehicle_id가 이미 있으면 손대지 않고, vehicle_no가 없거나 마스터가 없으면 미지정 유지."""
    if not vehicle.vehicle_no:
        vehicle.client_vehicle_id = None
        return
    cv = (
        db.query(ClientVehicle.vehicle_id)
        .filter(ClientVehicle.vehicle_no == vehicle.vehicle_no)
        .first()
    )
    vehicle.client_vehicle_id = cv[0] if cv else None


def _vehicle_out(v: ProjectVehicle, client_names: dict) -> schemas.ProjectVehicleOut:
    out = schemas.ProjectVehicleOut.model_validate(v, from_attributes=True)
    return out.model_copy(update={"client_name": client_names.get(v.client_id)})


def _vehicle_rollup(db: Session, project_id: str):
    """사업 참여 차량 집계 — (대수, 총감축량). _project_detail·목록 공용."""
    rows = db.query(ProjectVehicle.total_reduction).filter(
        ProjectVehicle.project_id == project_id
    ).all()
    total = round(sum(float(r[0]) for r in rows if r[0] is not None), 3)
    return len(rows), total


# ── 거래계약(매수자별 선물 판매) + 내부 차액 수익 파생 ─────────────────────
_SALE_FIELDS = (
    "buyer_name", "buyer_id", "buyer_type", "sale_unit_price", "quantity",
    "ownership_pct", "sale_invoice_amount", "sale_invoice_date", "is_hold",
    "contract_date", "memo",
)


def _resolve_buyer(db: Session, buyer_id: Optional[str]) -> Optional["Buyer"]:
    """거래계약의 buyer_id 존재 검증 — 값이 있으면 매수자 마스터를 반환(없으면 404)."""
    if not buyer_id:
        return None
    return common.get_or_404(db, Buyer, buyer_id, "매수자")


def _sale_out(s: ProjectSale) -> schemas.ProjectSaleOut:
    return schemas.ProjectSaleOut.model_validate(s, from_attributes=True)


def _project_sales(db: Session, project_id: str):
    """사업 거래계약 목록 — 등록순(created_at asc)."""
    return (
        db.query(ProjectSale)
        .filter(ProjectSale.project_id == project_id)
        .order_by(ProjectSale.created_at.asc(), ProjectSale.sale_id.asc())
        .all()
    )


def _sale_amount(sales) -> Optional[float]:
    """매출 Σ(판매단가 × 수량) — 단가·수량 둘 다 입력된 계약만. 계산가능분 없으면 None."""
    parts = [
        float(s.sale_unit_price) * float(s.quantity)
        for s in sales
        if s.sale_unit_price is not None and s.quantity is not None
    ]
    return round(sum(parts), 2) if parts else None


def _payout_amount(db: Session, project_id: str) -> Optional[float]:
    """지급 Σ(차량 expected_payout, None 제외) — 전건 None이면 None."""
    total = (
        db.query(func.sum(ProjectVehicle.expected_payout))
        .filter(ProjectVehicle.project_id == project_id)
        .scalar()
    )
    return round(float(total), 2) if total is not None else None


def _product_amount(db: Session, project_id: str) -> float:
    """제품(총매입) Σ(매입세금계산서 금액, None 제외) — 없으면 0(부록 L.3)."""
    total = (
        db.query(func.sum(PurchaseInvoice.amount))
        .filter(PurchaseInvoice.project_id == project_id)
        .scalar()
    )
    return round(float(total), 2) if total is not None else 0.0


def _validate_ownership_total(db: Session, project_id: str, new_pct: Optional[float],
                              exclude_sale_id: Optional[str] = None):
    """Σ 소유권비율 > 100.01 시 422 — 후시보유 포함 100% 초과 방지(부록 L.3)."""
    if new_pct is None:
        return
    query = db.query(func.coalesce(func.sum(ProjectSale.ownership_pct), 0)).filter(
        ProjectSale.project_id == project_id
    )
    if exclude_sale_id:
        query = query.filter(ProjectSale.sale_id != exclude_sale_id)
    current_total = float(query.scalar() or 0)
    if current_total + float(new_pct) > 100.01:
        raise HTTPException(
            status_code=422,
            detail="소유권비율 합계가 100%를 초과합니다 (현재 {0:g}% + 신규 {1:g}%)".format(
                current_total, float(new_pct)
            ),
        )


# ── 차량 파생값 정본 산식(부록 L) — 단가 미사용 ──────────────────────────────
# 엑셀 v19.3 정본과 1:1 일치가 목표. 예상지급액은 최대지급액(차량당 상한) × 감축량비 ×
# 잔여차령비로 산출한다(원가 톤당 단가 미사용).
DEFAULT_BASE_REDUCTION = 240.0  # 기준감축량 기본값
DEFAULT_BASE_VEHICLE_AGE = 8.0  # 기준차령 기본값


def _add_months(d: date, months: int) -> date:
    """월 단위 가감(엑셀 EDATE 상당) — 말일 오버플로는 해당 월 말일로 절사."""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _expire_at(registered_at) -> Optional[date]:
    """차령만료일 — EDATE(등록일, 12*9) - 1일. 등록일 없으면 None."""
    if registered_at is None:
        return None
    return _add_months(registered_at, 108) - timedelta(days=1)


def _remaining_age(expire_at, approved_at, base_age: float) -> Optional[float]:
    """잔여차령 — MIN(기준차령, (만료일-승인일)/365). 만료일·승인일 없으면 None."""
    if expire_at is None or approved_at is None:
        return None
    return min(base_age, (expire_at - approved_at).days / 365.0)


def _effective_reduction(reductions, remaining_age, base_reduction: float) -> Optional[float]:
    """잔여반영감축량 — MIN(기준감축량, Σ 연차감축량×clamp(잔여차령-k, 0, 1)).

    reductions: [y1..y10](None은 0 취급). remaining_age None이면 None.
    """
    if remaining_age is None:
        return None
    weighted = 0.0
    for k in range(10):
        y = reductions[k]
        if y is None:
            continue
        w = min(1.0, max(0.0, remaining_age - k))  # clamp(잔여차령-k, 0, 1)
        weighted += float(y) * w
    return min(base_reduction, weighted)


def _expected_payout(max_payment, effective_reduction, remaining_age,
                     base_reduction: float, base_vehicle_age: float) -> Optional[float]:
    """예상지급액 — 최대지급액 × (잔여반영감축량/기준감축량) × (잔여차령/기준차령), 원 단위 절사(TRUNC).

    구성 요소가 하나라도 없으면 None(미정). Numeric(15,2)를 초과하면 422 — DB 오류(500) 사전 차단.
    """
    if max_payment is None or effective_reduction is None or remaining_age is None:
        return None
    val = float(max_payment) * (effective_reduction / base_reduction) * (remaining_age / base_vehicle_age)
    amount = float(math.trunc(val))  # 원 단위 절사(TRUNC)
    if abs(amount) >= common.EXPECTED_AMOUNT_LIMIT:
        raise HTTPException(
            status_code=422,
            detail="예상 지급액이 허용 범위를 초과합니다 — 최대지급액·감축량 단위를 확인하세요",
        )
    return amount


def _derive_vehicle(project: Project, vehicle: ProjectVehicle) -> None:
    """단일 차량 전체 파생값 재계산(부록 L 정본) — total_reduction·만료일·잔여차령·
    잔여반영감축량·예상지급액을 순수 파생값으로 채운다(수기 입력 없음).
    """
    base_r = float(project.base_reduction) if project.base_reduction else DEFAULT_BASE_REDUCTION  # 0/None → 기본(0 나눗셈 방어)
    base_a = float(project.base_vehicle_age) if project.base_vehicle_age else DEFAULT_BASE_VEHICLE_AGE
    reductions = [getattr(vehicle, f) for f in _REDUCTION_YEARS]
    vehicle.total_reduction = _sum_reductions(vehicle)  # 연차 단순합(유지)
    vehicle.expire_at = _expire_at(vehicle.registered_at)
    vehicle.remaining_age = _remaining_age(vehicle.expire_at, project.approved_at, base_a)
    vehicle.effective_reduction = _effective_reduction(reductions, vehicle.remaining_age, base_r)
    vehicle.expected_payout = _expected_payout(
        project.max_payment, vehicle.effective_reduction, vehicle.remaining_age, base_r, base_a
    )


def _recalc_vehicle_payouts(db: Session, project: Project) -> None:
    """부록 L — 사업 전체 차량의 파생값을 재적재(수기 입력 없음).

    지급 파라미터(최대지급액·기준감축량·기준차령)·승인일 변경 등 파생 경로에서 공통 적용.
    구성 요소 미입력 시 해당 차량 파생값은 None(미정).
    """
    vehicles = (
        db.query(ProjectVehicle)
        .filter(ProjectVehicle.project_id == project.project_id)
        .all()
    )
    for v in vehicles:
        _derive_vehicle(project, v)


def _project_detail(db: Session, project: Project) -> schemas.ProjectDetailOut:
    unames = common.user_name_map(db, [project.manager_id])
    stages, delayed_count = _stage_outs(db, project)
    vehicle_count, total_reduction = _vehicle_rollup(db, project.project_id)
    # 거래계약 + 내부 차액 수익 파생 — 매출Σ(판매단가×수량) − 지급Σ(차량 expected_payout)
    sales = _project_sales(db, project.project_id)
    sale_amount = _sale_amount(sales)
    payout_amount = _payout_amount(db, project.project_id)
    margin_amount = (
        round(sale_amount - payout_amount, 2)
        if sale_amount is not None and payout_amount is not None
        else None
    )
    margin_ratio = (
        round(margin_amount / sale_amount * 100, 2)
        if margin_amount is not None and sale_amount is not None and sale_amount > 0
        else None
    )
    # 회계 원장층 파생(부록 L.3) — 제품(총매입)·예상지급액(payout_amount 재사용)·거래계약 실발행액
    acct = accounting.compute_accounting(
        approval_status=project.approval_status,
        product=_product_amount(db, project.project_id),
        expected_payment=payout_amount,
        sales=sales,
    )
    out = schemas.ProjectDetailOut.model_validate(project, from_attributes=True)
    return out.model_copy(
        update={
            "manager_name": unames.get(project.manager_id),
            "stages": stages,
            "delayed_stage_count": delayed_count,
            "vehicle_count": vehicle_count,
            "total_reduction": total_reduction,
            "sales": [_sale_out(s) for s in sales],
            "sale_amount": sale_amount,
            "payout_amount": payout_amount,
            "margin_amount": margin_amount,
            "margin_ratio": margin_ratio,
            **acct,
        }
    )


@router.get("", response_model=schemas.ProjectListResponse)
def list_projects(
    project_status: Optional[str] = Query(None, description="기획/등록완료/모니터링/검증/발급완료"),
    manager_id: Optional[str] = Query(None, description="담당 PM"),
    mon_cycle: Optional[str] = Query(None, description="모니터링 주기"),
    search: Optional[str] = Query(None, description="사업명·고유번호 검색"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """사업 목록 (SCR-06) — 예상 발급일(D-day 계산용)·진행 단계 지연 수 포함."""
    query = db.query(Project)
    if project_status:
        query = query.filter(Project.project_status == project_status)
    if manager_id:
        query = query.filter(Project.manager_id == manager_id)
    if mon_cycle:
        query = query.filter(Project.mon_cycle == mon_cycle)
    if search:
        keyword = "%{0}%".format(common.escape_like(search.strip()))
        query = query.filter(
            Project.project_name.ilike(keyword, escape="\\")
            | Project.reg_code.ilike(keyword, escape="\\")
        )

    total = query.count()
    rows = (
        query.order_by(Project.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    ids = [p.project_id for p in rows]
    unames = common.user_name_map(db, [p.manager_id for p in rows])

    # 지연 단계 수 — 목록 대상 프로젝트의 단계를 한 번에 조회해 파이썬에서 판정(N+1 회피)
    delay_map = {}
    if ids:
        today = date.today()
        for st in db.query(ProjectStage).filter(ProjectStage.project_id.in_(ids)):
            if st.planned_date and st.actual_date is None and st.planned_date < today:
                delay_map[st.project_id] = delay_map.get(st.project_id, 0) + 1

    items = [
        schemas.ProjectListItem.model_validate(p, from_attributes=True).model_copy(
            update={
                "manager_name": unames.get(p.manager_id),
                "delayed_stage_count": delay_map.get(p.project_id, 0),
            }
        )
        for p in rows
    ]
    return schemas.ProjectListResponse(items=items, total=total)


@router.get("/stage-delays", response_model=schemas.ProjectStageAlertsOut)
def project_stage_delays(
    imminent_days: int = Query(7, ge=1, le=60),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """진행 단계 지연/임박 관찰 (Phase 1 대시보드 위젯) — 경영전략실 대응용.

    지연 = 예정 경과 & 미도달, 임박 = 예정이 imminent_days 이내 & 미도달.
    (경로가 /{project_id}보다 먼저 등록되도록 목록 바로 뒤에 정의)
    """
    today = date.today()
    stages = (
        db.query(ProjectStage)
        .filter(ProjectStage.planned_date.isnot(None), ProjectStage.actual_date.is_(None))
        .all()
    )
    pnames = {
        p.project_id: p.project_name
        for p in db.query(Project.project_id, Project.project_name)
    }
    delayed, imminent = [], []
    for s in stages:
        name = pnames.get(s.project_id)
        if name is None:
            continue  # 삭제된 사업의 유령 단계 방어(정상 경로에선 자식 삭제로 발생 안 함)
        gap = (s.planned_date - today).days
        if gap < 0:
            delayed.append(
                schemas.ProjectStageAlert(
                    project_id=s.project_id,
                    project_name=name,
                    stage_code=s.stage_code,
                    planned_date=s.planned_date,
                    days=-gap,
                )
            )
        elif gap <= imminent_days:
            imminent.append(
                schemas.ProjectStageAlert(
                    project_id=s.project_id,
                    project_name=name,
                    stage_code=s.stage_code,
                    planned_date=s.planned_date,
                    days=gap,
                )
            )
    delayed.sort(key=lambda a: a.days, reverse=True)  # 오래 지연된 것부터
    imminent.sort(key=lambda a: a.days)  # 임박한 것부터
    return schemas.ProjectStageAlertsOut(delayed=delayed, imminent=imminent)


# 파생값 정합 감사(DBA P1.4)에서 비교할 저장 파생 필드 — before/after 키 정본
_DERIVED_FIELDS = ("total_reduction", "effective_reduction", "remaining_age", "expected_payout")


def _to_float(v) -> Optional[float]:
    """Numeric/None → float/None (None은 '미정'으로 그대로 유지)."""
    return None if v is None else float(v)


@router.get("/integrity/vehicles", response_model=schemas.VehicleIntegrityReport)
def audit_vehicle_integrity(
    _: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """차량 파생값 정합 감사(DBA P1.4) — 저장된 파생값이 재계산과 어긋나는(stale) 차량을 탐지만.

    읽기전용 진단: DB 트리거가 없어 파라미터 변경 경로가 재계산을 빠뜨리면 stale이 생긴다.
    저장은 절대 하지 않는다 — 재계산은 in-memory mutation이므로 autoflush로 우발 persist되지
    않도록 (1) 차량을 전부 선조회(루프 내 추가 쿼리 금지), (2) db.no_autoflush 블록에서 계산,
    (3) 마지막에 반드시 db.rollback()으로 변경을 폐기한다.
    (경로가 /{project_id}보다 먼저 매칭되도록 목록/알림 뒤에 정의)
    """
    projects = {p.project_id: p for p in db.query(Project).all()}
    vehicles = db.query(ProjectVehicle).all()  # 전부 선조회 — 루프 내 쿼리는 autoflush 유발

    checked = 0
    stale = 0
    samples: List[dict] = []
    with db.no_autoflush:  # 재계산 mutation이 flush로 persist되지 않도록
        for v in vehicles:
            project = projects.get(v.project_id)
            if project is None:
                continue  # 고아 차량(정상 경로엔 없음) — 감사 대상 아님
            checked += 1
            before = {f: _to_float(getattr(v, f)) for f in _DERIVED_FIELDS}
            try:
                _derive_vehicle(project, v)  # in-memory 재계산(저장 안 함, 아래 rollback)
            except HTTPException as exc:
                # _expected_payout 상한 초과 등 개별 차량 실패 — 중단 없이 stale로 집계
                stale += 1
                if len(samples) < 20:
                    samples.append({
                        "vehicle_id": v.vehicle_id,
                        "project_id": v.project_id,
                        "error": getattr(exc, "detail", str(exc)),
                    })
                continue
            after = {f: _to_float(getattr(v, f)) for f in _DERIVED_FIELDS}
            diffs = {}
            for f in _DERIVED_FIELDS:
                b, a = before[f], after[f]
                if b is None or a is None:
                    mismatch = b is not a  # None은 정확히 일치해야 함(양쪽 None만 OK)
                else:
                    mismatch = abs(b - a) > 1e-3  # 허용오차 절대 1e-3
                if mismatch:
                    diffs[f] = {"before": b, "after": a}
            if diffs:
                stale += 1
                if len(samples) < 20:
                    samples.append({
                        "vehicle_id": v.vehicle_id,
                        "project_id": v.project_id,
                        **diffs,
                    })
    db.rollback()  # 계산상 변경 전부 폐기 — 감사는 절대 저장하지 않음
    return schemas.VehicleIntegrityReport(checked=checked, stale=stale, samples=samples)


@router.post("", response_model=schemas.ProjectDetailOut, status_code=201)
def create_project(
    payload: schemas.ProjectCreate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """사업 등록 (SCR-06) — 진행 단계를 PROJECT_STATUS 코드별로 자동 시드."""
    validate_active_code(db, "PROJECT_STATUS", payload.project_status)
    if payload.approval_status:
        validate_active_code(db, "APPROVAL_STATUS", payload.approval_status)
    if payload.client_id:
        common.get_or_404(db, Client, payload.client_id, "고객사")
    if payload.manager_id:
        common.get_or_404(db, User, payload.manager_id, "담당 PM")
    project = Project(**{f: getattr(payload, f) for f in _PROJECT_FIELDS})
    db.add(project)
    db.flush()  # PK(gen_uuid)는 flush 시점에 생성 — 감사 대상 ID 확보
    _seed_stages(db, project)  # 진행 단계 5행 자동 시드(Phase 1)
    AuditLogger.log_action(
        db,
        user.user_id,
        "PROJECT_CREATE",
        target_type="PROJECT",
        target_id=project.project_id,
    )
    db.commit()
    db.refresh(project)
    return _project_detail(db, project)


@router.get("/{project_id}", response_model=schemas.ProjectDetailOut)
def get_project(
    project_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """사업 상세 (SCR-06) — 개요 + 참여 고객사 매핑 목록 + 진행 단계."""
    project = common.get_or_404(db, Project, project_id, "감축 사업")
    _seed_stages(db, project)  # 레거시 프로젝트 단계 지연 보강(멱등)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # 동시 최초 시드 경합 — 이미 시드됨(uq_project_stage_slot)
    return _project_detail(db, project)


@router.put("/{project_id}", response_model=schemas.ProjectDetailOut)
def update_project(
    project_id: str,
    payload: schemas.ProjectUpdate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """사업 수정 — 전달된 필드만 반영. 진행 상태 전이 시 해당 단계 도달일 자동 기록."""
    project = common.get_or_404(db, Project, project_id, "감축 사업")
    data = payload.model_dump(exclude_unset=True)
    if "project_status" in data:
        validate_active_code(db, "PROJECT_STATUS", data["project_status"])
    if data.get("approval_status"):
        validate_active_code(db, "APPROVAL_STATUS", data["approval_status"])
    if data.get("client_id"):
        common.get_or_404(db, Client, data["client_id"], "고객사")
    if data.get("manager_id"):
        common.get_or_404(db, User, data["manager_id"], "담당 PM")
    old_status = project.project_status  # 실제 전이 판정용 — setattr 전에 스냅샷
    for field in _PROJECT_FIELDS:
        if field in data:
            setattr(project, field, data[field])
    # 진행 상태가 '실제로' 바뀔 때만 해당 단계의 실제 도달일 자동 기록(비어 있을 때만) — Phase 1.
    # (폼이 수정 시에도 project_status를 항상 재전송하므로, 값이 동일하면 도달일을 찍지 않아
    #  기존 지연 상태가 조용히 해제되는 것을 방지)
    if "project_status" in data and data["project_status"] != old_status:
        _seed_stages(db, project)
        db.flush()
        stage = (
            db.query(ProjectStage)
            .filter(
                ProjectStage.project_id == project.project_id,
                ProjectStage.stage_code == data["project_status"],
            )
            .first()
        )
        if stage is not None and stage.actual_date is None:
            stage.actual_date = date.today()

    # 감사 로그는 커밋 전에 적재해야 함께 저장된다 (커밋 후 add는 유실)
    AuditLogger.log_action(
        db,
        user.user_id,
        "PROJECT_UPDATE",
        target_type="PROJECT",
        target_id=project.project_id,
    )
    db.commit()
    db.refresh(project)
    return _project_detail(db, project)


@router.put("/{project_id}/stages", response_model=schemas.ProjectDetailOut)
def update_project_stages(
    project_id: str,
    payload: schemas.ProjectStagesUpdate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """진행 단계 예정일/실제일 편집 (Phase 1) — 전달된 필드만 반영."""
    project = common.get_or_404(db, Project, project_id, "감축 사업")
    _seed_stages(db, project)
    db.flush()
    valid = {code for code, _ in _project_status_codes(db)}
    existing = {
        s.stage_code: s
        for s in db.query(ProjectStage).filter(
            ProjectStage.project_id == project_id
        )
    }
    for item in payload.stages:
        if item.stage_code not in valid:
            raise HTTPException(
                status_code=422,
                detail="유효한 진행 단계가 아닙니다: {0}".format(item.stage_code),
            )
        stage = existing.get(item.stage_code)
        if stage is None:
            continue
        fields_set = item.model_fields_set  # 전달된 필드만 갱신(부분 편집)
        if "planned_date" in fields_set:
            stage.planned_date = item.planned_date
        if "actual_date" in fields_set:
            stage.actual_date = item.actual_date
    AuditLogger.log_action(
        db,
        user.user_id,
        "PROJECT_STAGE_UPDATE",
        target_type="PROJECT",
        target_id=project_id,
    )
    db.commit()
    db.refresh(project)
    return _project_detail(db, project)


# ── 사업 참여 차량 (Phase 2 — 감축량·예상지급액 ingest) ────────────────────
def _client_names(db: Session, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {
        cid: name
        for cid, name in db.query(Client.client_id, Client.company_name).filter(
            Client.client_id.in_(ids)
        )
    }


@router.get(
    "/{project_id}/operators", response_model=schemas.ProjectOperatorListResponse
)
def list_project_operators(
    project_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """참여 운수사 롤업 — 참여 차량을 운수사(client_id)별 (차량수·잔여반영감축량 합·예상지급액 합)."""
    common.get_or_404(db, Project, project_id, "감축 사업")
    rows = (
        db.query(
            ProjectVehicle.client_id,
            func.count(ProjectVehicle.vehicle_id),
            func.coalesce(func.sum(ProjectVehicle.effective_reduction), 0),
            func.sum(ProjectVehicle.expected_payout),
        )
        .filter(ProjectVehicle.project_id == project_id)
        .group_by(ProjectVehicle.client_id)
        .all()
    )
    cnames = _client_names(db, [r[0] for r in rows])
    items = [
        schemas.ProjectOperatorRollup(
            client_id=cid,
            client_name=cnames.get(cid) if cid else "미지정",
            vehicle_count=count,
            total_reduction=round(float(reduction or 0), 3),
            total_expected_payout=round(float(payout), 2) if payout is not None else None,
        )
        for cid, count, reduction, payout in rows
    ]
    # 차량수 desc, 그다음 운수사명(오름차순) — 미지정은 client_name "미지정"으로 정렬 참여
    items.sort(key=lambda i: (-i.vehicle_count, i.client_name or ""))
    return schemas.ProjectOperatorListResponse(items=items, total=len(items))


@router.get("/{project_id}/vehicles", response_model=schemas.ProjectVehicleListResponse)
def list_project_vehicles(
    project_id: str,
    search: Optional[str] = Query(None, description="차량번호·운수사명 검색"),
    client_id: Optional[str] = Query(None, description="운수사 필터(롤업 펼침용)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """사업 참여 차량 목록(페이지·검색) + 총감축량·예상지급액 합계(필터 기준)."""
    common.get_or_404(db, Project, project_id, "감축 사업")
    base = db.query(ProjectVehicle).filter(ProjectVehicle.project_id == project_id)
    if client_id == "__none__":
        base = base.filter(ProjectVehicle.client_id.is_(None))  # 미지정 운수사 드릴다운
    elif client_id:
        base = base.filter(ProjectVehicle.client_id == client_id)
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
        base = base.filter(or_(*conds))

    total = base.count()
    agg = base.with_entities(
        func.coalesce(func.sum(ProjectVehicle.total_reduction), 0),
        func.sum(ProjectVehicle.expected_payout),
    ).one()
    rows = (
        # created_at 동률(대량 엑셀 등록 시 동일 타임스탬프) 대비 vehicle_id 타이브레이커 —
        # 페이지 경계에서 행 누락/중복 방지
        base.order_by(ProjectVehicle.created_at.asc(), ProjectVehicle.vehicle_id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    cnames = _client_names(db, [v.client_id for v in rows])
    return schemas.ProjectVehicleListResponse(
        items=[_vehicle_out(v, cnames) for v in rows],
        total=total,
        total_reduction=round(float(agg[0] or 0), 3),
        total_expected_payout=round(float(agg[1]), 2) if agg[1] is not None else None,
    )


@router.post(
    "/{project_id}/vehicles", response_model=schemas.ProjectVehicleOut, status_code=201
)
def create_project_vehicle(
    project_id: str,
    payload: schemas.ProjectVehicleIn,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """차량 등록 — 도입구분 검증, 파생값(연차 합·만료일·잔여차령·예상지급액) 서버 계산(부록 L)."""
    project = common.get_or_404(db, Project, project_id, "감축 사업")
    if payload.introduction_type:
        validate_active_code(db, "VEHICLE_INTRO", payload.introduction_type)
    if payload.region:
        validate_active_code(db, "REGION", payload.region)
    if payload.client_id:
        common.get_or_404(db, Client, payload.client_id, "운수사")
    if payload.asset_id:
        common.get_or_404(db, Asset, payload.asset_id, "자산")
    vehicle = ProjectVehicle(
        project_id=project_id, **{f: getattr(payload, f) for f in _VEHICLE_FIELDS}
    )
    _derive_vehicle(project, vehicle)  # 파생값 일괄 계산(부록 L)
    _link_client_vehicle(db, vehicle)  # fleet 마스터 링크(참여 구분, 부록 M)
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return _vehicle_out(vehicle, _client_names(db, [vehicle.client_id]))


@router.put(
    "/{project_id}/vehicles/{vehicle_id}", response_model=schemas.ProjectVehicleOut
)
def update_project_vehicle(
    project_id: str,
    vehicle_id: str,
    payload: schemas.ProjectVehicleIn,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """차량 수정 — 전달된 필드만 반영, 파생값 재계산(부록 L)."""
    vehicle = (
        db.query(ProjectVehicle)
        .filter(
            ProjectVehicle.project_id == project_id,
            ProjectVehicle.vehicle_id == vehicle_id,
        )
        .first()
    )
    if vehicle is None:
        raise HTTPException(status_code=404, detail="차량을 찾을 수 없습니다")
    data = payload.model_dump(exclude_unset=True)
    if data.get("introduction_type"):
        validate_active_code(db, "VEHICLE_INTRO", data["introduction_type"])
    if data.get("region"):
        validate_active_code(db, "REGION", data["region"])
    if data.get("client_id"):
        common.get_or_404(db, Client, data["client_id"], "운수사")
    if data.get("asset_id"):
        common.get_or_404(db, Asset, data["asset_id"], "자산")
    for field in _VEHICLE_FIELDS:
        if field in data:
            setattr(vehicle, field, data[field])
    project = common.get_or_404(db, Project, project_id, "감축 사업")
    _derive_vehicle(project, vehicle)  # 파생값 일괄 재계산(부록 L)
    if "vehicle_no" in data:  # 차량번호 변경 시 fleet 마스터 링크 재설정(부록 M)
        _link_client_vehicle(db, vehicle)
    db.commit()
    db.refresh(vehicle)
    return _vehicle_out(vehicle, _client_names(db, [vehicle.client_id]))


@router.delete(
    "/{project_id}/vehicles/{vehicle_id}", response_model=schemas.MessageResponse
)
def delete_project_vehicle(
    project_id: str,
    vehicle_id: str,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    vehicle = (
        db.query(ProjectVehicle)
        .filter(
            ProjectVehicle.project_id == project_id,
            ProjectVehicle.vehicle_id == vehicle_id,
        )
        .first()
    )
    if vehicle is None:
        raise HTTPException(status_code=404, detail="차량을 찾을 수 없습니다")
    db.delete(vehicle)
    db.commit()
    return schemas.MessageResponse(message="차량이 삭제되었습니다")


_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_VEHICLE_IMPORT_ENTITY = "project_vehicles"


@router.get("/{project_id}/vehicles/template")
def download_vehicle_template(
    project_id: str,
    _: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """차량 일괄등록 양식(.xlsx) — 헤더+예시 1행(도입구분·지역은 현재 라벨)."""
    common.get_or_404(db, Project, project_id, "감축 사업")
    spec = excel_import.get_spec(_VEHICLE_IMPORT_ENTITY)
    content = excel_import.build_template(db, _VEHICLE_IMPORT_ENTITY)
    return Response(
        content=content,
        media_type=_XLSX_MEDIA,
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''{0}".format(
                quote(spec.filename)
            )
        },
    )


@router.post(
    "/{project_id}/vehicles/commit", response_model=schemas.ImportCommitOut
)
async def commit_vehicle_import(
    project_id: str,
    file: UploadFile = File(...),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """차량 엑셀 일괄 등록 — 유효 행만 project_id로 삽입(파생값 서버 계산, 부록 L).

    오류 행은 건너뛰고(errors 안내) 감사 로그에 건수만 남긴다(R2-E6)."""
    project = common.get_or_404(db, Project, project_id, "감축 사업")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="빈 파일은 업로드할 수 없습니다")
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="파일 크기가 25MB를 초과합니다")
    result = excel_import.parse_and_validate(db, _VEHICLE_IMPORT_ENTITY, content)
    # fleet 마스터 링크용 선조회(차량번호→마스터 id, 부록 M) — 대량 대비 1회 로드
    fleet_by_no = {
        no: vid
        for vid, no in db.query(ClientVehicle.vehicle_id, ClientVehicle.vehicle_no)
        if no
    }
    created, empty = 0, 0
    for parsed in result.valid_rows:
        fields = {f: getattr(parsed.payload, f) for f in _VEHICLE_FIELDS}
        # 전 컬럼이 비면(헤더 불일치·빈 행) '빈 차량' 삽입 방지 — project_vehicles는
        # 필수 컬럼이 없어 파서 가드가 안 걸리므로 여기서 방어(리뷰 지적).
        if all(v is None for v in fields.values()):
            empty += 1
            continue
        vehicle = ProjectVehicle(project_id=project_id, **fields)
        _derive_vehicle(project, vehicle)  # 파생값 일괄 계산(부록 L)
        if vehicle.vehicle_no:  # fleet 마스터 링크(참여 구분, 부록 M)
            vehicle.client_vehicle_id = fleet_by_no.get(vehicle.vehicle_no)
        db.add(vehicle)
        created += 1
    error_rows = [r for r in result.rows if r.errors]
    skipped = len(error_rows) + empty
    AuditLogger.log_action(
        db,
        user.user_id,
        "EXCEL_IMPORT",
        target_type="PROJECT_VEHICLE",
        target_id=project_id,
        new_value="사업 참여 차량 일괄 등록 — 생성 {0}건 / 건너뜀 {1}건 (총 {2}행)".format(
            created, skipped, len(result.rows)
        ),
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # 검증~반영 사이 참조(운수사 등) 삭제 경합 — 배치 무산, 재시도 안내
        raise HTTPException(
            status_code=409,
            detail="참조 데이터가 변경되어 반영하지 못했습니다. 다시 시도해 주세요.",
        )
    return schemas.ImportCommitOut(
        entity=_VEHICLE_IMPORT_ENTITY,
        created=created,
        skipped=skipped,
        errors=[excel_import.row_result(r) for r in error_rows],
    )


# ── 거래계약(매수자별 선물 판매) CRUD ─────────────────────────────────────
@router.get("/{project_id}/sales", response_model=schemas.ProjectSaleListResponse)
def list_project_sales(
    project_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """거래계약 목록(등록순) + 매출 합계(Σ 판매단가×수량, 둘 다 입력된 계약만)."""
    common.get_or_404(db, Project, project_id, "감축 사업")
    sales = _project_sales(db, project_id)
    return schemas.ProjectSaleListResponse(
        items=[_sale_out(s) for s in sales],
        total=len(sales),
        total_sale_amount=_sale_amount(sales),
    )


@router.post(
    "/{project_id}/sales", response_model=schemas.ProjectSaleOut, status_code=201
)
def create_project_sale(
    project_id: str,
    payload: schemas.ProjectSaleIn,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """거래계약 등록 — buyer_type은 SALE_BUYER_TYPE 공통코드 검증."""
    common.get_or_404(db, Project, project_id, "감축 사업")
    if payload.buyer_type:
        validate_active_code(db, "SALE_BUYER_TYPE", payload.buyer_type)
    buyer = _resolve_buyer(db, payload.buyer_id)  # buyer_id 있으면 존재 검증
    _validate_ownership_total(db, project_id, payload.ownership_pct)  # 소유권비율 합 100% 초과 방지
    sale = ProjectSale(
        project_id=project_id, **{f: getattr(payload, f) for f in _SALE_FIELDS}
    )
    if buyer is not None:  # 마스터 연결 시 표기명 동기화(표시 일관)
        sale.buyer_name = buyer.name
    db.add(sale)
    db.flush()  # PK(gen_uuid)는 flush 시점 생성 — 감사 대상 ID 확보
    # 감사 로그 — 매수자·단가는 매출 축(원가단가와 한 레코드 병기 금지, H.6)
    AuditLogger.log_action(
        db,
        user.user_id,
        "PROJECT_SALE_CREATE",
        target_type="PROJECT_SALE",
        target_id=sale.sale_id,
    )
    db.commit()
    db.refresh(sale)
    return _sale_out(sale)


@router.put(
    "/{project_id}/sales/{sale_id}", response_model=schemas.ProjectSaleOut
)
def update_project_sale(
    project_id: str,
    sale_id: str,
    payload: schemas.ProjectSaleUpdate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """거래계약 수정 — 전달된 필드만 반영."""
    sale = (
        db.query(ProjectSale)
        .filter(
            ProjectSale.project_id == project_id,
            ProjectSale.sale_id == sale_id,
        )
        .first()
    )
    if sale is None:
        raise HTTPException(status_code=404, detail="거래계약을 찾을 수 없습니다")
    data = payload.model_dump(exclude_unset=True)
    if data.get("buyer_type"):
        validate_active_code(db, "SALE_BUYER_TYPE", data["buyer_type"])
    buyer = _resolve_buyer(db, data["buyer_id"]) if data.get("buyer_id") else None
    if "ownership_pct" in data:
        _validate_ownership_total(db, project_id, data["ownership_pct"], exclude_sale_id=sale_id)
    for field in _SALE_FIELDS:
        if field in data:
            setattr(sale, field, data[field])
    if buyer is not None:  # 마스터 연결 시 표기명 동기화(표시 일관)
        sale.buyer_name = buyer.name
    AuditLogger.log_action(
        db,
        user.user_id,
        "PROJECT_SALE_UPDATE",
        target_type="PROJECT_SALE",
        target_id=sale.sale_id,
    )
    db.commit()
    db.refresh(sale)
    return _sale_out(sale)


@router.delete(
    "/{project_id}/sales/{sale_id}", response_model=schemas.MessageResponse
)
def delete_project_sale(
    project_id: str,
    sale_id: str,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """거래계약 삭제."""
    sale = (
        db.query(ProjectSale)
        .filter(
            ProjectSale.project_id == project_id,
            ProjectSale.sale_id == sale_id,
        )
        .first()
    )
    if sale is None:
        raise HTTPException(status_code=404, detail="거래계약을 찾을 수 없습니다")
    db.delete(sale)
    AuditLogger.log_action(
        db,
        user.user_id,
        "PROJECT_SALE_DELETE",
        target_type="PROJECT_SALE",
        target_id=sale_id,
    )
    db.commit()
    return schemas.MessageResponse(message="거래계약이 삭제되었습니다")


# ── 매입세금계산서(운수사 실지급=제품) CRUD — 회계 원장층 제품 원천(부록 L.3) ──
_INVOICE_FIELDS = ("client_id", "operator_name", "region", "issue_date", "amount", "memo")
_INVOICE_IMPORT_ENTITY = "purchase_invoices"


def _invoice_out(inv: PurchaseInvoice, client_names: dict) -> schemas.PurchaseInvoiceOut:
    out = schemas.PurchaseInvoiceOut.model_validate(inv, from_attributes=True)
    return out.model_copy(update={"client_name": client_names.get(inv.client_id)})


def _project_invoices(db: Session, project_id: str):
    """매입세금계산서 목록 — 등록순(created_at asc, invoice_id 타이브레이커)."""
    return (
        db.query(PurchaseInvoice)
        .filter(PurchaseInvoice.project_id == project_id)
        .order_by(PurchaseInvoice.created_at.asc(), PurchaseInvoice.invoice_id.asc())
        .all()
    )


@router.get(
    "/{project_id}/purchase-invoices",
    response_model=schemas.PurchaseInvoiceListResponse,
)
def list_purchase_invoices(
    project_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """매입세금계산서 목록(등록순) + 제품(총매입) 합계(Σ 금액)."""
    common.get_or_404(db, Project, project_id, "감축 사업")
    invoices = _project_invoices(db, project_id)
    cnames = _client_names(db, [i.client_id for i in invoices])
    total_amount = (
        round(sum(float(i.amount) for i in invoices if i.amount is not None), 2)
        if any(i.amount is not None for i in invoices)
        else None
    )
    return schemas.PurchaseInvoiceListResponse(
        items=[_invoice_out(i, cnames) for i in invoices],
        total=len(invoices),
        total_amount=total_amount,
    )


@router.post(
    "/{project_id}/purchase-invoices",
    response_model=schemas.PurchaseInvoiceOut,
    status_code=201,
)
def create_purchase_invoice(
    project_id: str,
    payload: schemas.PurchaseInvoiceIn,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """매입세금계산서 등록 — 운수사·지역 검증, 금액 필수(제품=Σ 금액, 부록 L.3)."""
    common.get_or_404(db, Project, project_id, "감축 사업")
    if payload.region:
        validate_active_code(db, "REGION", payload.region)
    if payload.client_id:
        common.get_or_404(db, Client, payload.client_id, "운수사")
    invoice = PurchaseInvoice(
        project_id=project_id, **{f: getattr(payload, f) for f in _INVOICE_FIELDS}
    )
    db.add(invoice)
    db.flush()  # PK(gen_uuid)는 flush 시점 생성 — 감사 대상 ID 확보
    AuditLogger.log_action(
        db,
        user.user_id,
        "PURCHASE_INVOICE_CREATE",
        target_type="PURCHASE_INVOICE",
        target_id=invoice.invoice_id,
    )
    db.commit()
    db.refresh(invoice)
    return _invoice_out(invoice, _client_names(db, [invoice.client_id]))


@router.put(
    "/{project_id}/purchase-invoices/{invoice_id}",
    response_model=schemas.PurchaseInvoiceOut,
)
def update_purchase_invoice(
    project_id: str,
    invoice_id: str,
    payload: schemas.PurchaseInvoiceUpdate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """매입세금계산서 수정 — 전달된 필드만 반영."""
    invoice = (
        db.query(PurchaseInvoice)
        .filter(
            PurchaseInvoice.project_id == project_id,
            PurchaseInvoice.invoice_id == invoice_id,
        )
        .first()
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="매입세금계산서를 찾을 수 없습니다")
    data = payload.model_dump(exclude_unset=True)
    if data.get("region"):
        validate_active_code(db, "REGION", data["region"])
    if data.get("client_id"):
        common.get_or_404(db, Client, data["client_id"], "운수사")
    for field in _INVOICE_FIELDS:
        if field in data:
            setattr(invoice, field, data[field])
    AuditLogger.log_action(
        db,
        user.user_id,
        "PURCHASE_INVOICE_UPDATE",
        target_type="PURCHASE_INVOICE",
        target_id=invoice.invoice_id,
    )
    db.commit()
    db.refresh(invoice)
    return _invoice_out(invoice, _client_names(db, [invoice.client_id]))


@router.delete(
    "/{project_id}/purchase-invoices/{invoice_id}",
    response_model=schemas.MessageResponse,
)
def delete_purchase_invoice(
    project_id: str,
    invoice_id: str,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """매입세금계산서 삭제."""
    invoice = (
        db.query(PurchaseInvoice)
        .filter(
            PurchaseInvoice.project_id == project_id,
            PurchaseInvoice.invoice_id == invoice_id,
        )
        .first()
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="매입세금계산서를 찾을 수 없습니다")
    db.delete(invoice)
    AuditLogger.log_action(
        db,
        user.user_id,
        "PURCHASE_INVOICE_DELETE",
        target_type="PURCHASE_INVOICE",
        target_id=invoice_id,
    )
    db.commit()
    return schemas.MessageResponse(message="매입세금계산서가 삭제되었습니다")


@router.get("/{project_id}/purchase-invoices/template")
def download_purchase_invoice_template(
    project_id: str,
    _: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """매입세금계산서 일괄등록 양식(.xlsx) — 헤더+예시 1행(지역은 현재 라벨)."""
    common.get_or_404(db, Project, project_id, "감축 사업")
    spec = excel_import.get_spec(_INVOICE_IMPORT_ENTITY)
    content = excel_import.build_template(db, _INVOICE_IMPORT_ENTITY)
    return Response(
        content=content,
        media_type=_XLSX_MEDIA,
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''{0}".format(
                quote(spec.filename)
            )
        },
    )


@router.post(
    "/{project_id}/purchase-invoices/commit",
    response_model=schemas.ImportCommitOut,
)
async def commit_purchase_invoice_import(
    project_id: str,
    file: UploadFile = File(...),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """매입세금계산서 엑셀 일괄 등록 — 유효 행만 project_id로 삽입.

    오류 행은 건너뛰고(errors 안내) 감사 로그에 건수만 남긴다(R2-E6)."""
    common.get_or_404(db, Project, project_id, "감축 사업")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="빈 파일은 업로드할 수 없습니다")
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="파일 크기가 25MB를 초과합니다")
    result = excel_import.parse_and_validate(db, _INVOICE_IMPORT_ENTITY, content)
    created = 0
    for parsed in result.valid_rows:
        fields = {f: getattr(parsed.payload, f) for f in _INVOICE_FIELDS}
        invoice = PurchaseInvoice(project_id=project_id, **fields)
        db.add(invoice)
        created += 1
    error_rows = [r for r in result.rows if r.errors]
    skipped = len(error_rows)
    AuditLogger.log_action(
        db,
        user.user_id,
        "EXCEL_IMPORT",
        target_type="PURCHASE_INVOICE",
        target_id=project_id,
        new_value="매입세금계산서 일괄 등록 — 생성 {0}건 / 건너뜀 {1}건 (총 {2}행)".format(
            created, skipped, len(result.rows)
        ),
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # 검증~반영 사이 참조(운수사 등) 삭제 경합 — 배치 무산, 재시도 안내
        raise HTTPException(
            status_code=409,
            detail="참조 데이터가 변경되어 반영하지 못했습니다. 다시 시도해 주세요.",
        )
    return schemas.ImportCommitOut(
        entity=_INVOICE_IMPORT_ENTITY,
        created=created,
        skipped=skipped,
        errors=[excel_import.row_result(r) for r in error_rows],
    )


@router.delete("/{project_id}", response_model=schemas.MessageResponse)
def delete_project(
    project_id: str,
    user: User = Depends(require_permission("client.delete")),
    db: Session = Depends(get_db),
):
    """사업 삭제 — MANAGER 이상(§10.1). 자식 행(단계·차량·거래계약·매입계산서)을 함께 정리."""
    project = common.get_or_404(db, Project, project_id, "감축 사업")
    # 진행 단계·참여 차량 자식 행 정리 — 없으면 Postgres FK 위반으로 삭제 실패(Phase 1·2)
    db.query(ProjectStage).filter(
        ProjectStage.project_id == project_id
    ).delete(synchronize_session=False)
    db.query(ProjectVehicle).filter(
        ProjectVehicle.project_id == project_id
    ).delete(synchronize_session=False)
    # 거래계약 자식 행 정리 — 없으면 Postgres FK 위반으로 삭제 실패
    db.query(ProjectSale).filter(
        ProjectSale.project_id == project_id
    ).delete(synchronize_session=False)
    # 매입세금계산서 자식 행 정리 — 없으면 Postgres FK 위반으로 삭제 실패(회계 원장층)
    db.query(PurchaseInvoice).filter(
        PurchaseInvoice.project_id == project_id
    ).delete(synchronize_session=False)
    db.delete(project)

    AuditLogger.log_action(
        db,
        user.user_id,
        "PROJECT_DELETE",
        target_type="PROJECT", 
        target_id=project.project_id
    )
    
    db.commit()
    return schemas.MessageResponse(message="감축 사업이 삭제되었습니다")


@router.put("/{project_id}/payout-params", response_model=schemas.ProjectDetailOut)
def update_payout_params(
    project_id: str,
    payload: schemas.PayoutParamsUpdate,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """지급 파라미터 수기 입력(부록 L) — expected_payout 파생 기준(단가 미사용).

    최대지급액·기준감축량·기준차령·승인일 중 전달된 것만 반영한다. 최대지급액을 세팅할 때
    기준감축량·기준차령이 아직 미설정(None)이면 각각 240·8로 초기화한다. 승인일 미전달 &
    미승인 상태면 승인 시점으로 간주해 오늘로 자동 세팅한다. 파라미터 변경 시 해당 사업 전체
    차량의 파생값(예상지급액 등)을 재계산해 적재한다(순수 파생). null 전달 시 미정.
    """
    project = common.get_or_404(db, Project, project_id, "감축 사업")
    data = payload.model_dump(exclude_unset=True)
    old_max = project.max_payment
    if "max_payment" in data:
        project.max_payment = data["max_payment"]
        # 최대지급액 세팅 시 기준값 미설정이면 정본 기본값(240/8)으로 초기화
        if project.base_reduction is None:
            project.base_reduction = DEFAULT_BASE_REDUCTION
        if project.base_vehicle_age is None:
            project.base_vehicle_age = DEFAULT_BASE_VEHICLE_AGE
    if "base_reduction" in data:
        project.base_reduction = data["base_reduction"]
    if "base_vehicle_age" in data:
        project.base_vehicle_age = data["base_vehicle_age"]
    if payload.approved_at is not None:
        project.approved_at = payload.approved_at
    elif project.approved_at is None:
        project.approved_at = date.today()  # 지급 파라미터 입력 = 승인 시점(미설정 시)
    _recalc_vehicle_payouts(db, project)
    # 감사 로그 — 최대지급액만 old→new 기록(다른 파라미터 병기 금지, R2-E6/H.6)
    new_max = data.get("max_payment") if "max_payment" in data else old_max
    AuditLogger.log_action(
        db,
        user.user_id,
        "PROJECT_PAYOUT_PARAMS",
        target_type="PROJECT",
        target_id=project.project_id,
        old_value="{0:g}".format(float(old_max)) if old_max is not None else None,
        new_value="{0:g}".format(float(new_max)) if new_max is not None else None,
    )
    db.commit()
    db.refresh(project)
    return _project_detail(db, project)
