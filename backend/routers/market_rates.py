"""매출단가 시세 마스터(effective-dated) — 톤당 단가의 시점별 이력 등록·조회.

현재 시세 = 유효일자 ≤ 오늘 중 최신 단가(services.market_rate.current_market_rate).
매출단가는 내부 재무정보 → 조회도 내부 인증(get_current_user)만 허용하고, 외부역할
(PARTNER/INVESTOR)은 PERMISSION_MATRIX 미등록이라 자동 403(원천 차단). 등록은 master.write.
실현매출·회계 원장(부록 L.3)과 무관한 참조성 마스터다(과거 불변).
"""

from datetime import date
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import MarketRate, User, get_db
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/market-rates", tags=["market-rates"])


@router.get("", response_model=List[schemas.MarketRateOut])
def list_market_rates(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """시세 이력 목록(유효일자 최신순). 이력 소량 전제로 전체 반환."""
    return (
        db.query(MarketRate)
        .order_by(
            MarketRate.effective_date.desc(),
            MarketRate.created_at.desc(),
            MarketRate.rate_id.desc(),
        )
        .all()
    )


@router.get("/current")
def get_current_rate(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """현재 시세 — 유효일자 ≤ 오늘 중 최신 단가. 이력 없으면 null.

    단가만 필요한 재사용처(증분3 재고평가)는 services.market_rate.current_market_rate를
    쓴다. 여기서는 effective_date까지 함께 노출하므로 해당 행 1건을 직접 조회한다.
    """
    row = (
        db.query(MarketRate)
        .filter(MarketRate.effective_date <= date.today())
        .order_by(
            MarketRate.effective_date.desc(),
            MarketRate.created_at.desc(),
            MarketRate.rate_id.desc(),
        )
        .first()
    )
    if row is None:
        return None
    return {"effective_date": row.effective_date, "unit_price": float(row.unit_price)}


@router.post("", response_model=schemas.MarketRateOut, status_code=201)
def create_market_rate(
    payload: schemas.MarketRateIn,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """시세 등록 — 같은 effective_date 재등록은 append 허용(이력 보존, 조회는 최신 우선)."""
    rate = MarketRate(
        effective_date=payload.effective_date,
        unit_price=payload.unit_price,
        note=payload.note,
        created_by=user.user_id,
    )
    db.add(rate)
    db.flush()  # rate_id 확보(감사 target_id)
    AuditLogger.log_action(
        db,
        user.user_id,
        "MARKET_RATE_CREATE",
        target_type="MARKET_RATE",
        target_id=rate.rate_id,
        new_value=str(payload.unit_price),
    )
    db.commit()
    db.refresh(rate)
    return rate
