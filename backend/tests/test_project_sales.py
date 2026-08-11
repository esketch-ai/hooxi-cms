"""거래계약(매수자별 선물 판매단가) + 내부 차액 수익 파생 — CRUD·집계·차액·정리."""

API = "/api/v1"
PROJECTS = API + "/projects"


def _mk_project(client, headers, name):
    r = client.post(PROJECTS, headers=headers, json={"project_name": name, "project_status": "기획"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def test_sale_buyer_type_codes_seeded(client, staff_headers):
    r = client.get(API + "/codes", headers=staff_headers, params={"category": "SALE_BUYER_TYPE"})
    assert r.status_code == 200, r.text
    codes = {c["code"] for c in r.json()}
    assert {"증권사", "투자사", "금융사"} <= codes


def test_create_sale_and_list_totals(client, staff_headers):
    pid = _mk_project(client, staff_headers, "거래계약목록검증")
    r = client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "증권X", "buyer_type": "증권사", "sale_unit_price": 15000, "quantity": 3000},
    )
    assert r.status_code == 201, r.text
    assert r.json()["buyer_name"] == "증권X"
    # 수량 없는 계약 — total_sale_amount 합산 제외
    client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "금융Y", "sale_unit_price": 14800},
    )
    lr = client.get(f"{PROJECTS}/{pid}/sales", headers=staff_headers).json()
    assert lr["total"] == 2
    assert lr["total_sale_amount"] == 45000000  # 15000×3000 (금융Y는 수량 없어 제외)


def test_invalid_buyer_type_422(client, staff_headers):
    pid = _mk_project(client, staff_headers, "매수자구분검증")
    r = client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "X", "buyer_type": "없는구분"},
    )
    assert r.status_code == 422, r.text


def _capped_vehicle(reduction_per_year):
    """잔여차령 8 캡 노후차 페이로드 — y1..y8 동일값(y9·y10 가중 0). 등록 2016-01-01."""
    p = {"registered_at": "2016-01-01"}
    for i in range(1, 9):
        p[f"reduction_y{i}"] = reduction_per_year
    return p


def test_margin_derivation_in_detail(client, staff_headers):
    """차액 = 매출(Σ 판매단가×수량) − 지급(Σ 차량 예상지급액 정본). 상세에 파생 표시."""
    pid = _mk_project(client, staff_headers, "차액파생검증")
    # 차량 2대(잔여차령 8 캡): y1..y8=30→eff 240, y1..y8=15→eff 120
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json=_capped_vehicle(30))
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json=_capped_vehicle(15))
    # 최대지급액 120만·승인일 → expected: 1,200,000 / 600,000 → payout 1,800,000
    client.put(
        f"{PROJECTS}/{pid}/payout-params",
        headers=staff_headers,
        json={"max_payment": 1200000, "approved_at": "2016-02-01"},
    )
    # 매출: 판매단가×수량 = 8000 × 300 = 2,400,000
    client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "증권X", "sale_unit_price": 8000, "quantity": 300},
    )
    d = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()
    assert d["payout_amount"] == 1800000  # 1,200,000 + 600,000 (정본 비례식, 캡)
    assert d["sale_amount"] == 2400000  # 8000 × 300
    assert d["margin_amount"] == 600000  # 2,400,000 − 1,800,000
    assert d["margin_ratio"] == 25.0  # 600000 / 2400000 × 100
    assert len(d["sales"]) == 1


def test_margin_none_without_prices(client, staff_headers):
    pid = _mk_project(client, staff_headers, "차액미산출검증")
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json={"reduction_y1": 10})
    d = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()
    # 단가·계약 없음 → 파생 불가
    assert d["payout_amount"] is None
    assert d["sale_amount"] is None
    assert d["margin_amount"] is None


def test_update_and_delete_sale(client, staff_headers):
    pid = _mk_project(client, staff_headers, "거래계약수정삭제")
    s = client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "증권X", "sale_unit_price": 15000, "quantity": 100},
    ).json()
    sid = s["sale_id"]
    r = client.put(
        f"{PROJECTS}/{pid}/sales/{sid}", headers=staff_headers, json={"sale_unit_price": 16000}
    )
    assert r.status_code == 200, r.text
    assert r.json()["sale_unit_price"] == 16000
    assert r.json()["buyer_name"] == "증권X"  # 부분 수정 — 미전달 필드 보존
    assert client.delete(f"{PROJECTS}/{pid}/sales/{sid}", headers=staff_headers).status_code == 200
    assert client.get(f"{PROJECTS}/{pid}/sales", headers=staff_headers).json()["total"] == 0


def test_delete_project_removes_sales(client, staff_headers, manager_headers):
    pid = _mk_project(client, staff_headers, "거래계약정리검증")
    client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "증권X", "sale_unit_price": 15000, "quantity": 100},
    )
    r = client.delete(f"{PROJECTS}/{pid}", headers=manager_headers)
    assert r.status_code == 200, r.text  # 거래계약 자식 있어도 FK 위반 없이 삭제


def test_project_no_longer_accepts_sale_unit_price(client, staff_headers):
    """단일 소스 — 프로젝트 단일 sale_unit_price 제거(거래계약으로 이관). 응답에 미노출."""
    pid = _mk_project(client, staff_headers, "매출단가제거검증")
    d = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()
    assert "sale_unit_price" not in d
