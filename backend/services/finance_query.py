"""재무 원장 조회층 — 사업(프로젝트) grain 배치 회계의 단일 진실원(T1).

여러 사업의 회계 원장값(부록 L.3, compute_accounting)을 **배치 조회**로 모아 사업별로
1회 계산한다(N+1 회피). asset_vehicles의 재무 KPI, finance_ledger 원장이 모두 이 함수를
공유해 산식·쿼리 관용구가 갈라지지 않게 한다.

조회 전용 — 신규 컬럼 없음. compute_accounting 풀 dict(12값)를 사업별로 그대로 반환한다.
"""

from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Project, ProjectSale, ProjectVehicle, PurchaseInvoice
from services import accounting


def _ownership_split(sales) -> Dict[str, float]:
    """후시(is_hold='Y')/계약(그 외) 소유권 분할 파생 — 조회 전용 add-only 키.

    수량은 round(_,3)·소유권비율은 round(_,2), 값 없으면 0.0 기본. held/sold 합은
    엔진 ownership_total(None 아닐 때)과 정합한다(held_ownership+sold_ownership==ownership_total).
    """
    held_qty = sum(
        float(s.quantity)
        for s in sales
        if s.is_hold == "Y" and s.quantity is not None
    )
    sold_qty = sum(
        float(s.quantity)
        for s in sales
        if s.is_hold != "Y" and s.quantity is not None
    )
    held_ownership = sum(
        float(s.ownership_pct)
        for s in sales
        if s.is_hold == "Y" and s.ownership_pct is not None
    )
    sold_ownership = sum(
        float(s.ownership_pct)
        for s in sales
        if s.is_hold != "Y" and s.ownership_pct is not None
    )
    return {
        "held_qty": round(held_qty, 3),
        "sold_qty": round(sold_qty, 3),
        "held_ownership": round(held_ownership, 2),
        "sold_ownership": round(sold_ownership, 2),
    }


def project_accounting_batch(
    db: Session, project_ids
) -> Dict[str, Dict[str, Optional[float]]]:
    """distinct 사업별 회계 집계(compute_accounting 풀 dict) — 사업당 1회, N+1 회피.

    projects.py 상세 경로와 동일 입력(제품=Σ매입, 예상지급액=Σ차량 expected_payout,
    거래계약 목록, 승인상태)을 각 in_ 1쿼리로 모아 사업별로 1회 계산한다.
    반환: {project_id: compute_accounting(...) 풀 dict(product·expected_payment·wip1·wip2·
    liability·inventory·payout_rate·sale_recognized·gross_profit·profit_rate·ownership_total)
    + 후시/계약 소유권 분할(held_qty·sold_qty·held_ownership·sold_ownership, add-only)}
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
    # 잔여반영감축량 Σ — 사업 전체 차량 기준(예상수익 leaf 조달, B2). payouts 배치 옆 add-only.
    # 전건 None이면 SUM→None(예상수익 None 전파). N+1 회피 위해 여기서 1쿼리로 함께 집계한다.
    eff_sums = dict(
        db.query(ProjectVehicle.project_id, func.sum(ProjectVehicle.effective_reduction))
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

    result: Dict[str, Dict[str, Optional[float]]] = {}
    for pid in ids:
        payout = payouts.get(pid)
        product = products.get(pid)
        sales = sales_by_pid.get(pid, [])
        acct = accounting.compute_accounting(
            approval_status=approvals.get(pid),
            product=round(float(product), 2) if product is not None else 0.0,
            expected_payment=round(float(payout), 2) if payout is not None else None,
            sales=sales,
        )
        # 후시/계약 소유권 분할 add-only(asset_vehicles는 revenue/cost/profit만 읽어 무영향)
        acct.update(_ownership_split(sales))
        # 잔여반영감축량 Σ add-only(B2, 예상수익 leaf 원천) — Numeric→float, 전건 None이면 None.
        # FinanceLedgerRow는 extra='ignore'라 이 키를 스프레드해도 무해(라우터가 명시 조달).
        e = eff_sums.get(pid)
        acct["effective_reduction_sum"] = float(e) if e is not None else None
        result[pid] = acct
    return result
