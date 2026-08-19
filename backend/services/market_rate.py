"""매출단가 시세 리졸버 — effective-dated 시세 이력의 "현재 시세" 조회.

현재 시세 = on_date(기본=오늘) 이하 effective_date 중 가장 최신 1건의 unit_price.
같은 effective_date 다건(append 이력)은 최신 등록(created_at)을 우선한다.
증분3의 재고평가에서 재사용한다(참조성 마스터, 실현매출·회계 미접촉).
"""

import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from models import MarketRate


def current_market_rate(db: Session, on_date: Optional[date] = None) -> Optional[Decimal]:
    """on_date(기본=date.today()) 이하 effective_date 중 최신 단가. 없으면 None."""
    if on_date is None:
        on_date = date.today()
    row = (
        db.query(MarketRate)
        .filter(MarketRate.effective_date <= on_date)
        .order_by(
            MarketRate.effective_date.desc(),
            MarketRate.created_at.desc(),
            MarketRate.rate_id.desc(),
        )
        .first()
    )
    return row.unit_price if row else None


def trailing_avg_rate(
    db: Session, months: int = 6, as_of: Optional[date] = None
) -> Optional[Decimal]:
    """as_of(기본=오늘)의 당월을 제외한 직전 `months`개월 각 월말 시세의 평균.

    각 월말일 기준 current_market_rate(effective_date ≤ 월말 최신 1건)를 조회해
    존재하는 시세만 모아 평균(Decimal)한다. 하나도 없으면 None.
    (추적 시작 6개월 미만이면 존재하는 월만으로 평균한다.)
    """
    if as_of is None:
        as_of = date.today()
    # 당월 1일에서 하루를 빼 전월 말일부터 시작(당월 제외).
    month_end = as_of.replace(day=1) - timedelta(days=1)
    rates = []
    for _ in range(months):
        rate = current_market_rate(db, month_end)
        if rate is not None:
            rates.append(rate)
        # 다음(더 이른) 월말일로 이동.
        month_end = month_end.replace(day=1) - timedelta(days=1)
    if not rates:
        return None
    return sum(rates) / Decimal(len(rates))


def expected_revenue(eff_sum, avg6) -> Optional[float]:
    """유효수량합 × 6개월평균시세를 원단위 절사(TRUNC)한 예상수익. None 전파."""
    if eff_sum is None or avg6 is None:
        return None
    return float(math.trunc(float(eff_sum) * float(avg6)))
