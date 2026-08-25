"""탄소배출권 원가·재고 정밀화 C1 — 승인시점 매출단가·확정수량 잠금 스냅샷."""

import json

import models

API = "/api/v1"
PROJECTS = API + "/projects"


def _mk_project(client, headers, name):
    r = client.post(PROJECTS, headers=headers, json={"project_name": name, "project_status": "기획"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def _add_vehicle(client, headers, pid):
    payload = {"registered_at": "2016-01-01", "reduction_y9": 5, "reduction_y10": 5}
    for i in range(1, 9):
        payload[f"reduction_y{i}"] = 10
    return client.post(f"{PROJECTS}/{pid}/vehicles", headers=headers, json=payload).json()


def test_approval_snapshot_locks_price_and_reduction(client, staff_headers):
    pid = _mk_project(client, staff_headers, "C1스냅샷검증")
    _add_vehicle(client, staff_headers, pid)
    # 승인 전: 스냅샷 없음
    d0 = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()
    assert d0["approved_unit_price"] is None and d0["approved_reduction"] is None

    # 지급 파라미터 입력 = 승인 전이 → 스냅샷 1회 잠금
    r = client.put(f"{PROJECTS}/{pid}/payout-params", headers=staff_headers,
                   json={"max_payment": 2000000, "approved_at": "2016-02-01"})
    assert r.status_code == 200, r.text
    d1 = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()
    # 매출 기준단가(기본 20,000) + 확정수량 = Σ effective_reduction(80)
    assert d1["approved_unit_price"] == 20000.0
    assert d1["approved_reduction"] == 80.0


def test_snapshot_immutable_after_config_change(client, staff_headers):
    """승인 후 설정 단가를 바꿔도 잠금값 불변(잠금 1회)."""
    pid = _mk_project(client, staff_headers, "C1불변검증")
    _add_vehicle(client, staff_headers, pid)
    client.put(f"{PROJECTS}/{pid}/payout-params", headers=staff_headers,
               json={"max_payment": 2000000, "approved_at": "2016-02-01"})
    locked = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()["approved_unit_price"]
    assert locked == 20000.0

    # 설정 단가 변경
    db = models.SessionLocal()
    try:
        db.merge(models.Config(config_key="project_base_params",
                               config_value=json.dumps({"sale_base_unit_price": 25000})))
        db.commit()
    finally:
        db.close()
    # 파라미터 재편집(재계산) → 승인 스냅샷은 그대로 20,000(불변)
    client.put(f"{PROJECTS}/{pid}/payout-params", headers=staff_headers,
               json={"base_reduction": 240})
    d = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()
    assert d["approved_unit_price"] == 20000.0  # 잠금값 불변
    # 정리
    db = models.SessionLocal()
    try:
        db.query(models.Config).filter(models.Config.config_key == "project_base_params").delete()
        db.commit()
    finally:
        db.close()


def test_config_sale_price_applies_at_approval(client, staff_headers):
    """승인 시점의 설정 단가가 잠금값이 된다."""
    db = models.SessionLocal()
    try:
        db.merge(models.Config(config_key="project_base_params",
                               config_value=json.dumps({"sale_base_unit_price": 22000})))
        db.commit()
    finally:
        db.close()
    pid = _mk_project(client, staff_headers, "C1설정단가검증")
    _add_vehicle(client, staff_headers, pid)
    client.put(f"{PROJECTS}/{pid}/payout-params", headers=staff_headers,
               json={"max_payment": 2000000, "approved_at": "2016-02-01"})
    d = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()
    assert d["approved_unit_price"] == 22000.0
    db = models.SessionLocal()
    try:
        db.query(models.Config).filter(models.Config.config_key == "project_base_params").delete()
        db.commit()
    finally:
        db.close()


def test_c2_ownership_split(client, staff_headers):
    """C2 — 매각률로 소유량 K를 매각 M·후시보유 L 분할 + 재고평가(원가단가)."""
    pid = _mk_project(client, staff_headers, "C2분할검증")
    _add_vehicle(client, staff_headers, pid)
    # 승인 → 확정수량 K=80(effective)
    client.put(f"{PROJECTS}/{pid}/payout-params", headers=staff_headers,
               json={"max_payment": 2000000, "approved_at": "2016-02-01"})
    # 매각률 89% 설정(엑셀 89% 매각 케이스)
    r = client.put(f"{PROJECTS}/{pid}", headers=staff_headers, json={"sale_ratio": 89})
    assert r.status_code == 200, r.text
    d = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()
    co = d["carbon_ownership"]
    assert co is not None
    assert co["sale_ratio"] == 89.0 and co["owned_quantity"] == 80.0
    assert co["sold_quantity"] == 71.2   # 80 × 0.89
    assert co["held_quantity"] == 8.8    # 80 − 71.2
    assert co["inventory_value"] == round(8.8 * 13888)  # 후시보유 × 원가단가


def test_c2_no_ratio_no_split(client, staff_headers):
    """매각률 미설정이면 소유량 분할 None."""
    pid = _mk_project(client, staff_headers, "C2미설정검증")
    _add_vehicle(client, staff_headers, pid)
    client.put(f"{PROJECTS}/{pid}/payout-params", headers=staff_headers,
               json={"max_payment": 2000000, "approved_at": "2016-02-01"})
    d = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()
    assert d["carbon_ownership"] is None


def test_c2_full_hold(client, staff_headers):
    """100% 후시보유(매각률 0) → M=0, L=K."""
    pid = _mk_project(client, staff_headers, "C2전량보유검증")
    _add_vehicle(client, staff_headers, pid)
    client.put(f"{PROJECTS}/{pid}/payout-params", headers=staff_headers,
               json={"max_payment": 2000000, "approved_at": "2016-02-01"})
    client.put(f"{PROJECTS}/{pid}", headers=staff_headers, json={"sale_ratio": 0})
    co = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()["carbon_ownership"]
    assert co["sold_quantity"] == 0.0 and co["held_quantity"] == 80.0


def test_c3_valuation_expected_when_pending(client, staff_headers):
    """C3 신청중(미승인) — 평가 basis=EXPECTED(예상수량×6개월평균가)."""
    pid = _mk_project(client, staff_headers, "C3신청중검증")
    _add_vehicle(client, staff_headers, pid)
    # 승인 파라미터로 effective 파생시키되 승인상태는 미승인 유지 위해 approval_status 명시 안 함
    client.put(f"{PROJECTS}/{pid}/payout-params", headers=staff_headers,
               json={"max_payment": 2000000, "approved_at": "2016-02-01"})
    d = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()
    cv = d["credit_valuation"]
    assert cv is not None and cv["basis"] == "EXPECTED"
    # 시세 미설정이면 단가 None → 평가액 None(수량은 Σeff=80)
    assert cv["quantity"] == 80.0


def test_c3_valuation_confirmed_when_approved(client, staff_headers):
    """C3 승인 — 평가 basis=CONFIRMED(확정수량×잠금가). 잠금가 20,000·확정수량 80 → 1,600,000."""
    pid = _mk_project(client, staff_headers, "C3승인검증")
    _add_vehicle(client, staff_headers, pid)
    client.put(f"{PROJECTS}/{pid}/payout-params", headers=staff_headers,
               json={"max_payment": 2000000, "approved_at": "2016-02-01"})
    # 승인 상태 전환
    client.put(f"{PROJECTS}/{pid}", headers=staff_headers, json={"approval_status": "승인"})
    d = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()
    cv = d["credit_valuation"]
    assert cv["basis"] == "CONFIRMED"
    assert cv["quantity"] == 80.0 and cv["unit_price"] == 20000.0
    assert cv["valuation"] == 1600000  # trunc(80 × 20000)
