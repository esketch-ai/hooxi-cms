"""탄소배출권 소유량 분할·재고평가(C2) — 카본크레딧실 정본 엑셀 L/M/재고자산 축.

사업 단위 매각률(%)로 소유량 K를 매각(M)·후시보유(L)로 분할하고, 후시보유분을 원가단가로
재고 평가한다(엑셀: 100% 매각→M=K,L=0 / 89% 매각→M=0.89K,L=0.11K / 100% 보유→L=K).
회계 원장(compute_accounting)과 독립 — 조회 시 계산만(비영속).
"""

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
