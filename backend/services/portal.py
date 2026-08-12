"""포털 전용 뷰 빌더 (Phase 4 INC-4 / 부록 N.3 기밀 매트릭스).

원칙: 뷰 스키마가 금지 필드를 아예 선언하지 않아 서버가 원천 미포함(마스킹 아님).
어느 뷰도 원가와 매출을 동시에 담지 않는다(H.6). 내부 ProjectDetailOut·
accounting.compute_accounting은 재사용/호출하지 않는다 — 회계(payout_rate)·원가
계열을 절대 조회하지 않는다.

- PARTNER(운수사): 자기 참여 차량만 집계(count·Σeffective_reduction·Σexpected_payout).
  매출·판매단가·마진·타 운수사 데이터 미조회.
- INVESTOR(투자/금융): 운수사별 감축량(익명 라벨)·총 계약매출·자기 계약만.
  예상지급액·원가·지급률·매출인식·회계 미조회.
"""

from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

import schemas
from models import Project, ProjectSale, ProjectVehicle
from routers.projects import _stage_outs  # 진행 단계·지연 산정 재사용(회계 미개입)


def _gross_revenue(sale: ProjectSale) -> Optional[float]:
    """계약 1건의 매출 gross — 실발행액 우선, 없으면 단가×수량. 둘 다 없으면 None.

    회계(payout_rate·매출인식)는 개입하지 않는 순수 계약 총액. 부록 L.3의 gross 정의와 일치.
    """
    if sale.sale_invoice_amount is not None:
        return round(float(sale.sale_invoice_amount), 2)
    if sale.sale_unit_price is not None and sale.quantity is not None:
        return round(float(sale.sale_unit_price) * float(sale.quantity), 2)
    return None


def build_partner_view(
    db: Session, project: Project, client_id: str
) -> schemas.PartnerPortalView:
    """운수사 포털 뷰 — 그 client_id의 참여 차량만 집계.

    다른 운수사 데이터·매출·회계는 조회하지 않는다. my_effective_reduction·
    my_expected_payout은 전건 None(미산정)이면 None을 전파한다.
    """
    stages, _delayed = _stage_outs(db, project)

    rows = (
        db.query(ProjectVehicle.effective_reduction, ProjectVehicle.expected_payout)
        .filter(
            ProjectVehicle.project_id == project.project_id,
            ProjectVehicle.client_id == client_id,
        )
        .all()
    )

    count = len(rows)
    eff_vals = [float(r[0]) for r in rows if r[0] is not None]
    pay_vals = [float(r[1]) for r in rows if r[1] is not None]
    my_effective_reduction = round(sum(eff_vals), 3) if eff_vals else None
    my_expected_payout = round(sum(pay_vals), 2) if pay_vals else None

    return schemas.PartnerPortalView(
        project_id=project.project_id,
        project_name=project.project_name,
        project_status=project.project_status,
        stages=stages,
        my_vehicle_count=count,
        my_effective_reduction=my_effective_reduction,
        my_expected_payout=my_expected_payout,
    )


def build_investor_view(
    db: Session, project: Project, buyer_id: Optional[str]
) -> schemas.InvestorPortalView:
    """투자/금융 포털 뷰 — 운수사별 감축량(익명)·총 계약매출·자기 계약만.

    payout/원가/지급률/매출인식/회계는 절대 조회하지 않는다(compute_accounting 미호출).
    operators_reduction은 client 이름 없이 감축량 내림차순 익명 라벨(운수사 1,2,…).
    my_contract는 buyer_id 매칭 계약(들)의 합; 미매칭이면 None.
    """
    stages, _delayed = _stage_outs(db, project)

    # 참여 운수사별 감축량 — client_id group_by, 이름 없이 익명 라벨(감축량 내림차순)
    grouped = (
        db.query(
            func.count(ProjectVehicle.vehicle_id),
            func.sum(func.coalesce(ProjectVehicle.effective_reduction, 0)),
        )
        .filter(ProjectVehicle.project_id == project.project_id)
        .group_by(ProjectVehicle.client_id)
        .all()
    )
    ops = sorted(
        ((int(cnt), round(float(eff), 3)) for cnt, eff in grouped),
        key=lambda t: t[1],
        reverse=True,
    )
    operators_reduction: List[dict] = [
        {
            "label": "운수사 {0}".format(idx),
            "vehicle_count": cnt,
            "effective_reduction": eff,
        }
        for idx, (cnt, eff) in enumerate(ops, start=1)
    ]

    # 총 잔여반영감축량 — 전건 None이면 None(참여 차량이 없거나 전부 미산정)
    eff_total = (
        db.query(func.sum(ProjectVehicle.effective_reduction))
        .filter(ProjectVehicle.project_id == project.project_id)
        .scalar()
    )
    total_effective_reduction = round(float(eff_total), 3) if eff_total is not None else None

    # 총 계약매출 gross — 실발행액 우선, 없으면 단가×수량. 계산가능분 없으면 None
    sales = (
        db.query(ProjectSale)
        .filter(ProjectSale.project_id == project.project_id)
        .all()
    )
    grosses = [g for g in (_gross_revenue(s) for s in sales) if g is not None]
    total_contract_revenue = round(sum(grosses), 2) if grosses else None

    # 자기 계약 — buyer_id 매칭 계약(들)의 합(본인 계약만). 미매칭이면 None
    my_contract: Optional[dict] = None
    if buyer_id:
        mine = [s for s in sales if s.buyer_id == buyer_id]
        if mine:
            qtys = [float(s.quantity) for s in mine if s.quantity is not None]
            prices = [float(s.sale_unit_price) for s in mine if s.sale_unit_price is not None]
            invs = [float(s.sale_invoice_amount) for s in mine if s.sale_invoice_amount is not None]
            my_grosses = [g for g in (_gross_revenue(s) for s in mine) if g is not None]
            my_contract = {
                "quantity": round(sum(qtys), 3) if qtys else None,
                "gross_revenue": round(sum(my_grosses), 2) if my_grosses else None,
                # 단가는 계약별 상이 — 단건이면 그 값, 복수면 대표 산출 대신 None(오도 방지)
                "sale_unit_price": prices[0] if len(prices) == 1 else None,
                "sale_invoice_amount": round(sum(invs), 2) if invs else None,
            }

    return schemas.InvestorPortalView(
        project_id=project.project_id,
        project_name=project.project_name,
        project_status=project.project_status,
        stages=stages,
        operators_reduction=operators_reduction,
        total_effective_reduction=total_effective_reduction,
        total_contract_revenue=total_contract_revenue,
        my_contract=my_contract,
    )
