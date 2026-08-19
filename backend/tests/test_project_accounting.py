"""P·B 회계 원장층 — 매입세금계산서·승인상태 미착품 전환·지급률·매출인식·매출이익 (부록 L.3)."""

API = "/api/v1"
PROJECTS = API + "/projects"


def _mk_project(client, headers, name):
    r = client.post(PROJECTS, headers=headers, json={"project_name": name, "project_status": "기획"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def _capped_vehicle(per_year):
    """잔여차령 8 캡 노후차 — y1..y8 동일값(잔여반영=Σ, y9·y10 가중 0). 등록 2016-01-01."""
    p = {"registered_at": "2016-01-01"}
    for i in range(1, 9):
        p[f"reduction_y{i}"] = per_year
    return p


def test_approval_status_codes_seeded(client, staff_headers):
    r = client.get(API + "/codes", headers=staff_headers, params={"category": "APPROVAL_STATUS"})
    assert r.status_code == 200, r.text
    assert {"미승인", "승인"} <= {c["code"] for c in r.json()}


def test_purchase_invoice_crud_and_total(client, staff_headers):
    pid = _mk_project(client, staff_headers, "매입세금계산서검증")
    for amt in (500000, 700000):
        r = client.post(
            f"{PROJECTS}/{pid}/purchase-invoices",
            headers=staff_headers,
            json={"operator_name": "운수사갑", "amount": amt, "issue_date": "2026-03-01"},
        )
        assert r.status_code == 201, r.text
    lr = client.get(f"{PROJECTS}/{pid}/purchase-invoices", headers=staff_headers).json()
    assert lr["total"] == 2
    assert lr["total_amount"] == 1200000  # 500,000 + 700,000 (분할 다건 합)


def test_accounting_chain(client, staff_headers):
    """예상지급액 1,800,000·매입 1,200,000·매출 실발행 3,000,000 시나리오 (부록 L.3 정본)."""
    pid = _mk_project(client, staff_headers, "회계체인검증")
    # 차량 2대(캡): expected_payout 1,200,000 + 600,000 = expected_payment 1,800,000
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json=_capped_vehicle(30))
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json=_capped_vehicle(15))
    client.put(
        f"{PROJECTS}/{pid}/payout-params",
        headers=staff_headers,
        json={"max_payment": 1200000, "approved_at": "2016-02-01"},
    )
    # 매입세금계산서(제품) = 1,200,000
    for amt in (500000, 700000):
        client.post(
            f"{PROJECTS}/{pid}/purchase-invoices",
            headers=staff_headers,
            json={"operator_name": "운수사갑", "amount": amt},
        )
    # 거래계약: 매출세금계산서 실발행 3,000,000, 소유권 100%
    client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "증권X", "sale_invoice_amount": 3000000, "ownership_pct": 100},
    )

    # 미승인(기본): 미착품1=예상지급액 전액, 미착품2=0
    d = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()
    assert d["expected_payment"] == 1800000
    assert d["product"] == 1200000
    assert d["wip1"] == 1800000  # 미승인 → 예상지급액 전액
    assert d["wip2"] == 0
    assert d["liability"] == 1800000
    assert d["inventory"] == 3000000  # 부채 1,800,000 + 제품 1,200,000
    assert d["payout_rate"] == 0.667  # round(1,200,000 / 1,800,000, 3)
    assert d["sale_recognized"] == 2001000  # trunc(3,000,000 × 0.667)
    assert d["gross_profit"] == 801000  # trunc(2,001,000 − 1,200,000)
    assert d["ownership_total"] == 100

    # 승인 전환 → 미착품2=예상지급액−매입, 미착품1=0
    r = client.put(f"{PROJECTS}/{pid}", headers=staff_headers, json={"approval_status": "승인"})
    assert r.status_code == 200, r.text
    d2 = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()
    assert d2["wip1"] == 0
    assert d2["wip2"] == 600000  # trunc(1,800,000 − 1,200,000)
    assert d2["liability"] == 600000
    assert d2["inventory"] == 1800000  # 600,000 + 1,200,000


def test_ownership_over_100_rejected(client, staff_headers):
    pid = _mk_project(client, staff_headers, "소유권합검증")
    client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "증권X", "ownership_pct": 60},
    )
    r = client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "금융Y", "ownership_pct": 50},  # 60+50=110 > 100
    )
    assert r.status_code == 422, r.text


def test_purchase_invoice_payment_date_roundtrip(client, staff_headers):
    """매입세금계산서 입금일(payment_date) create→get→update round-trip (정보성·nullable)."""
    pid = _mk_project(client, staff_headers, "매입입금일검증")
    r = client.post(
        f"{PROJECTS}/{pid}/purchase-invoices",
        headers=staff_headers,
        json={"operator_name": "운수사갑", "amount": 500000, "payment_date": "2026-04-10"},
    )
    assert r.status_code == 201, r.text
    inv_id = r.json()["invoice_id"]
    got = client.get(f"{PROJECTS}/{pid}/purchase-invoices", headers=staff_headers).json()
    row = next(i for i in got["items"] if i["invoice_id"] == inv_id)
    assert row["payment_date"] == "2026-04-10"
    # 수정 반영
    u = client.put(
        f"{PROJECTS}/{pid}/purchase-invoices/{inv_id}",
        headers=staff_headers,
        json={"payment_date": "2026-05-20"},
    )
    assert u.status_code == 200, u.text
    got2 = client.get(f"{PROJECTS}/{pid}/purchase-invoices", headers=staff_headers).json()
    row2 = next(i for i in got2["items"] if i["invoice_id"] == inv_id)
    assert row2["payment_date"] == "2026-05-20"


def test_project_sale_payment_date_roundtrip(client, staff_headers):
    """거래계약 매출세금계산서 입금일(sale_payment_date) create→get→update round-trip."""
    pid = _mk_project(client, staff_headers, "매출입금일검증")
    r = client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "증권X", "sale_payment_date": "2026-04-10"},
    )
    assert r.status_code == 201, r.text
    sale_id = r.json()["sale_id"]
    got = client.get(f"{PROJECTS}/{pid}/sales", headers=staff_headers).json()
    row = next(s for s in got["items"] if s["sale_id"] == sale_id)
    assert row["sale_payment_date"] == "2026-04-10"
    u = client.put(
        f"{PROJECTS}/{pid}/sales/{sale_id}",
        headers=staff_headers,
        json={"sale_payment_date": "2026-05-20"},
    )
    assert u.status_code == 200, u.text
    got2 = client.get(f"{PROJECTS}/{pid}/sales", headers=staff_headers).json()
    row2 = next(s for s in got2["items"] if s["sale_id"] == sale_id)
    assert row2["sale_payment_date"] == "2026-05-20"


def test_accounting_none_without_payout(client, staff_headers):
    """예상지급액 미산출(단가 게이트) 시 지급률·매출인식 None 전파, 제품은 산출."""
    pid = _mk_project(client, staff_headers, "회계게이트검증")
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json={"reduction_y1": 10})
    client.post(
        f"{PROJECTS}/{pid}/purchase-invoices",
        headers=staff_headers,
        json={"operator_name": "운수사갑", "amount": 300000},
    )
    d = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()
    assert d["product"] == 300000  # 매입은 단가 무관 산출
    assert d["expected_payment"] is None  # 최대지급액·승인일 미입력 → 미산출
    assert d["payout_rate"] is None
    assert d["sale_recognized"] is None
