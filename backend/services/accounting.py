"""P·B 회계 원장층 산식(부록 L.3 — 엑셀 v19.3와 16/16 검증 완료).

매입세금계산서(운수사 실지급=제품)와 거래계약 실발행액(매출)로 회계 체인을 세운다.
예상지급액(Σ 차량 expected_payout)은 이미 파생된 값을 그대로 받는다.

단가 게이트 정합(부록 L): 예상지급액이 미정(전건 None)이면 지급률·매출인식·매출이익도
None으로 전파한다. 제품(총매입)·소유권비율 합은 단가와 무관하게 산출 가능하다.
"""

import math
from typing import Dict, List, Optional


def _ownership_total(sales) -> Optional[float]:
    """Σ 소유권비율(%) — 입력된 계약만. 하나도 없으면 None."""
    parts = [float(s.ownership_pct) for s in sales if s.ownership_pct is not None]
    return round(sum(parts), 2) if parts else None


def compute_accounting(
    approval_status: Optional[str],
    product: float,
    expected_payment: Optional[float],
    sales: List,
) -> Dict[str, Optional[float]]:
    """회계 원장층 파생값(부록 L.3 정본 산식) — trunc(원 단위 절사)·round(_,3) 그대로.

    - approval_status: 사업 승인상태(APPROVAL_STATUS: 미승인/승인)
    - product: 제품(총매입) = Σ 매입세금계산서 금액(항상 산출 가능, 없으면 0)
    - expected_payment: 예상지급액 = Σ 차량 expected_payout(전건 None이면 None)
    - sales: 거래계약 목록(sale_invoice_amount·ownership_pct 사용)
    """
    approved = approval_status == "승인"
    ownership_total = _ownership_total(sales)

    # 예상지급액 미정 → 단가 게이트: 지급률·매출인식·매출이익 및 미착품 체인 None 전파
    if expected_payment is None:
        return {
            "product": product,
            "expected_payment": None,
            "wip1": None,
            "wip2": None,
            "liability": None,
            "inventory": None,
            "payout_rate": None,
            "sale_recognized": None,
            "gross_profit": None,
            "profit_rate": None,
            "ownership_total": ownership_total,
        }

    wip1 = expected_payment if not approved else 0.0
    wip2 = float(math.trunc(expected_payment - product)) if approved else 0.0
    liability = wip1 + wip2
    inventory = liability + product
    payout_rate = round(product / expected_payment, 3) if expected_payment else 0.0
    # 매출인식: 계약별 trunc(실발행액 × 지급률) 합을 다시 trunc.
    # 실발행액 있는 계약만, 후시보유(is_hold='Y')는 미판매 잔량이라 제외(부록 L.4).
    sale_recognized = float(
        math.trunc(
            sum(
                math.trunc(float(s.sale_invoice_amount) * payout_rate)
                for s in sales
                if s.sale_invoice_amount is not None and (s.is_hold or "N") != "Y"
            )
        )
    )
    gross_profit = float(math.trunc(sale_recognized - product))
    profit_rate = round(gross_profit / sale_recognized, 3) if sale_recognized else 0.0
    return {
        "product": product,
        "expected_payment": expected_payment,
        "wip1": wip1,
        "wip2": wip2,
        "liability": liability,
        "inventory": inventory,
        "payout_rate": payout_rate,
        "sale_recognized": sale_recognized,
        "gross_profit": gross_profit,
        "profit_rate": profit_rate,
        "ownership_total": ownership_total,
    }
