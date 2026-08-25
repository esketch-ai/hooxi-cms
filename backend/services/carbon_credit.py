"""탄소배출권 소유량 분할·재고평가(C2) — 카본크레딧실 정본 엑셀 L/M/재고자산 축.

사업 단위 매각률(%)로 소유량 K를 매각(M)·후시보유(L)로 분할하고, 후시보유분을 원가단가로
재고 평가한다(엑셀: 100% 매각→M=K,L=0 / 89% 매각→M=0.89K,L=0.11K / 100% 보유→L=K).
회계 원장(compute_accounting)과 독립 — 조회 시 계산만(비영속).
"""

import math
from typing import Dict, Optional


def compute_ownership(
    owned_quantity: Optional[float],
    sale_ratio: Optional[float],
    inventory_unit_price: Optional[float],
) -> Optional[Dict[str, Optional[float]]]:
    """소유량 K + 매각률 → {매각 M, 후시보유 L, 재고자산 평가}. 입력 결여 시 None.

    - owned_quantity(K): 승인 확정수량(approved_reduction) 또는 Σ effective_reduction
    - sale_ratio: 매각률(%) 0~100
    - inventory_unit_price: 재고 원가단가(원/톤) — 후시보유분 평가
    """
    if owned_quantity is None or sale_ratio is None:
        return None
    k = float(owned_quantity)
    ratio = max(0.0, min(100.0, float(sale_ratio)))
    sold = round(k * ratio / 100.0, 3)
    held = round(k - sold, 3)
    inventory_value = (
        round(held * float(inventory_unit_price))
        if inventory_unit_price is not None and held > 0
        else None
    )
    return {
        "sale_ratio": round(ratio, 2),
        "owned_quantity": round(k, 3),
        "sold_quantity": sold,
        "held_quantity": held,
        "inventory_value": inventory_value,
    }


def compute_valuation(
    approval_status: Optional[str],
    eff_sum: Optional[float],
    avg6_rate: Optional[float],
    approved_reduction: Optional[float],
    approved_unit_price: Optional[float],
) -> Dict[str, Optional[object]]:
    """탄소배출권 2상태 평가액(C3) — 신청중=예상수량×6개월평균가 / 승인=확정수량×승인시점 잠금가.

    ※ 기존 compute_accounting(엑셀 v19.3 16/16 검증)은 **무접촉** — 이 함수는 별도 파생 평가.
    - 신청중(미승인 또는 승인스냅샷 미비): 수량=Σ effective_reduction, 단가=6개월 평균시세(EXPECTED)
    - 승인(잠금 스냅샷 존재): 수량=approved_reduction, 단가=approved_unit_price(CONFIRMED)
    평가액 = TRUNC(수량 × 단가). 수량/단가 결여 시 None.
    """
    approved = approval_status == "승인"
    if approved and approved_reduction is not None and approved_unit_price is not None:
        basis = "CONFIRMED"
        qty: Optional[float] = float(approved_reduction)
        unit: Optional[float] = float(approved_unit_price)
    else:
        basis = "EXPECTED"
        qty = float(eff_sum) if eff_sum is not None else None
        unit = float(avg6_rate) if avg6_rate is not None else None
    valuation = (
        float(math.trunc(qty * unit)) if (qty is not None and unit is not None) else None
    )
    return {"basis": basis, "quantity": qty, "unit_price": unit, "valuation": valuation}


def compute_payment_tracking(
    expected_cost: Optional[float],
    paid_amount: Optional[float],
    invoice_count: int,
) -> Dict[str, Optional[object]]:
    """실지급 추적(C4) — 예상원가(Σ expected_payout) vs 실지급(Σ 매입세금계산서=증빙).

    원가 정의=운수사 지급액(expected_payout). 실지급=매입 세금계산서 발행액(TAX_INVOICE 연결).
    expected_cost None(지급 파라미터 미설정)이면 진행률·미지급 잔액 None 전파.
    """
    paid = float(paid_amount or 0)
    if expected_cost is None:
        return {"expected_cost": None, "paid_amount": paid, "invoice_count": invoice_count,
                "payment_progress": None, "unpaid_balance": None}
    exp = float(expected_cost)
    return {
        "expected_cost": exp,
        "paid_amount": paid,
        "invoice_count": invoice_count,
        "payment_progress": round(paid / exp * 100, 1) if exp else None,
        "unpaid_balance": round(exp - paid, 2),
    }
