"""매출단가 시세 리졸버 — effective-dated 시세 이력의 "현재 시세" 조회.

현재 시세 = on_date(기본=오늘) 이하 effective_date 중 가장 최신 1건의 unit_price.
같은 effective_date 다건(append 이력)은 최신 등록(created_at)을 우선한다.
증분3의 재고평가에서 재사용한다(참조성 마스터, 실현매출·회계 미접촉).
"""

from datetime import date
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
