"""재고평가 파생(비영속 read-only, P0-2 증분3) — 후시보유분 × 현재시세.

재고평가액 = Σ(is_hold='Y' 계약 quantity) × 현재 매출단가 시세(원단위 반올림). 시세 없거나
후시보유 없으면 None. 저장하지 않는 파생값이라 과거 데이터·실현매출·회계는 미접촉.
"""

import models

API = "/api/v1"
PROJECTS = API + "/projects"
RATES = API + "/market-rates"


def _clear_rates():
    """세션 공유 DB에서 시세 전삭제 — '시세 없음' 경로를 결정적으로 검증하기 위함."""
    db = models.SessionLocal()
    try:
        db.query(models.MarketRate).delete()
        db.commit()
    finally:
        db.close()


def _mk_project(client, headers, name):
    r = client.post(PROJECTS, headers=headers, json={"project_name": name, "project_status": "기획"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def _detail(client, headers, pid):
    r = client.get(f"{PROJECTS}/{pid}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_inventory_valuation_held_times_rate(client, admin_headers):
    """후시보유(is_hold='Y') 수량 합 × 현재시세 = 재고평가액. 비보유는 제외."""
    assert client.post(RATES, headers=admin_headers, json={"effective_date": "2026-01-01", "unit_price": 14000}).status_code == 201
    pid = _mk_project(client, admin_headers, "재고평가검증")
    # 후시보유 2건(1000 + 500 = 1500 tCO2), 비보유 1건(제외)
    client.post(f"{PROJECTS}/{pid}/sales", headers=admin_headers,
                json={"buyer_name": "보유A", "quantity": 1000, "is_hold": "Y"})
    client.post(f"{PROJECTS}/{pid}/sales", headers=admin_headers,
                json={"buyer_name": "보유B", "quantity": 500, "is_hold": "Y"})
    client.post(f"{PROJECTS}/{pid}/sales", headers=admin_headers,
                json={"buyer_name": "판매C", "sale_unit_price": 15000, "quantity": 2000, "is_hold": "N"})
    d = _detail(client, admin_headers, pid)
    assert d["current_market_rate"] == 14000
    assert d["inventory_valuation"] == 1500 * 14000  # 21,000,000


def test_inventory_valuation_none_without_rate(client, admin_headers):
    """시세 미등록이면 재고평가·현재시세 모두 None."""
    _clear_rates()
    pid = _mk_project(client, admin_headers, "시세없음검증")
    client.post(f"{PROJECTS}/{pid}/sales", headers=admin_headers,
                json={"buyer_name": "보유A", "quantity": 1000, "is_hold": "Y"})
    d = _detail(client, admin_headers, pid)
    assert d["current_market_rate"] is None
    assert d["inventory_valuation"] is None


def test_inventory_valuation_none_without_hold(client, admin_headers):
    """후시보유 계약이 없으면 시세가 있어도 재고평가는 None."""
    assert client.post(RATES, headers=admin_headers, json={"effective_date": "2026-01-01", "unit_price": 14000}).status_code == 201
    pid = _mk_project(client, admin_headers, "보유없음검증")
    client.post(f"{PROJECTS}/{pid}/sales", headers=admin_headers,
                json={"buyer_name": "판매C", "sale_unit_price": 15000, "quantity": 2000, "is_hold": "N"})
    d = _detail(client, admin_headers, pid)
    assert d["current_market_rate"] == 14000
    assert d["inventory_valuation"] is None
