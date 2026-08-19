"""매출단가 시세 6개월 이동평균 + 예상수익 헬퍼(B1) — 순수 서비스 로직 검증.

trailing_avg_rate: as_of 당월을 제외한 직전 6개월 각 월말 시세의 평균(존재분만).
expected_revenue: 유효수량합 × 6개월평균을 원단위 절사(TRUNC), None 전파.
시점 의존을 피하기 위해 as_of를 고정해 검증한다(오늘 의존 회피).
"""

from datetime import date

import pytest

import models
from services.market_rate import expected_revenue, trailing_avg_rate


@pytest.fixture(autouse=True)
def _isolate_market_rates(client):
    """세션 공유 DB 격리 — 이 모듈이 시세 테이블을 통제된 상태로 쓰고, 끝나면
    원래 있던 행을 그대로 복원한다(뒤에 실행되는 시세/재고 테스트에 누수 방지)."""
    db = models.SessionLocal()
    try:
        saved = [
            {c.name: getattr(r, c.name) for c in models.MarketRate.__table__.columns}
            for r in db.query(models.MarketRate).all()
        ]
        db.query(models.MarketRate).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = models.SessionLocal()
    try:
        db.query(models.MarketRate).delete()
        for row in saved:
            db.add(models.MarketRate(**row))
        db.commit()
    finally:
        db.close()


def _reset_rates(db):
    """각 테스트 시작 시 시세 테이블을 비운다(테스트 간 상호 격리)."""
    db.query(models.MarketRate).delete()
    db.commit()


def _add_rate(db, effective, unit_price):
    db.add(models.MarketRate(effective_date=date.fromisoformat(effective), unit_price=unit_price))
    db.commit()


def test_trailing_avg_full_six_months():
    # (a) 직전 6개월 각 월에 유효시세 → 6개 평균이 정확
    #     as_of=2026-08-15 → 대상 월말 07/06/05/04/03/02
    db = models.SessionLocal()
    try:
        _reset_rates(db)
        for eff, price in [
            ("2026-02-01", 100), ("2026-03-01", 200), ("2026-04-01", 300),
            ("2026-05-01", 400), ("2026-06-01", 500), ("2026-07-01", 600),
        ]:
            _add_rate(db, eff, price)
        avg = trailing_avg_rate(db, months=6, as_of=date(2026, 8, 15))
        assert avg is not None
        assert float(avg) == 350.0  # (100+200+300+400+500+600)/6
    finally:
        db.close()


def test_trailing_avg_partial_history():
    # (b) 추적 시작 6개월 미만 → 존재하는 월만 평균(≥1)
    db = models.SessionLocal()
    try:
        _reset_rates(db)
        _add_rate(db, "2026-06-01", 500)
        _add_rate(db, "2026-07-01", 600)
        avg = trailing_avg_rate(db, months=6, as_of=date(2026, 8, 15))
        assert avg is not None
        assert float(avg) == 550.0  # (500+600)/2, 앞선 4개월은 이력 없음
    finally:
        db.close()


def test_trailing_avg_no_rates_is_none():
    # (c) 시세가 하나도 없으면 None
    db = models.SessionLocal()
    try:
        _reset_rates(db)
        assert trailing_avg_rate(db, months=6, as_of=date(2026, 8, 15)) is None
    finally:
        db.close()


def test_trailing_avg_excludes_current_month():
    # (d) 당월 시세는 평균에서 제외 — 당월에만 시세가 있으면 None
    db = models.SessionLocal()
    try:
        _reset_rates(db)
        _add_rate(db, "2026-08-05", 999)
        assert trailing_avg_rate(db, months=6, as_of=date(2026, 8, 15)) is None
    finally:
        db.close()


def test_expected_revenue_trunc_and_none():
    # (e) None 전파 + 원단위 절사(TRUNC)
    assert expected_revenue(None, 1000) is None
    assert expected_revenue(100.5, None) is None
    # 100.5 * 1000 = 100500.0 (정수), 소수 버림 확인용으로 avg에 소수 포함
    assert expected_revenue(100.5, 1000) == 100500.0
    assert expected_revenue(3, 3.9) == 11.0  # 11.7 → 11 절사
