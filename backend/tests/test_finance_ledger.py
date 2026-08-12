"""재무 원장(카본크레딧실 재무 전용, FL-1) — 사업 grain 조회 + 전사 총계.

- 총계 == Σ 행(사업 grain 단순합), None 전파(예상지급액 전건 None),
  필터(approval_status·buyer_id·invoice_from/to·is_hold) 좁힘 + 총계 재계산,
  distinct(join 유발 필터에도 사업 행 중복 없음), 외부역할(PARTNER) 403.
- 회계값 정합은 사업 상세(project detail, compute_accounting 동일 원천)와 교차 검증한다.
"""

import models

API = "/api/v1"
PROJECTS = API + "/projects"
LEDGER = API + "/finance-ledger"


def _mk_project(client, headers, name, approval_status=None):
    body = {"project_name": name, "project_status": "기획"}
    if approval_status:
        body["approval_status"] = approval_status
    r = client.post(PROJECTS, headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def _capped_vehicle(per_year, cid):
    """잔여차령 8 캡 노후차(등록 2016-01-01, y1..y8 동일값) — client_id 배정."""
    p = {"registered_at": "2016-01-01", "client_id": cid}
    for i in range(1, 9):
        p["reduction_y{0}".format(i)] = per_year
    return p


def _mk_client(client, headers, tag):
    r = client.post(API + "/clients", headers=headers,
                    json={"client_type": "TRANSPORT", "company_name": "재무운수" + tag})
    assert r.status_code == 201, r.text
    return r.json()["client_id"]


def _mk_buyer(client, headers, name):
    r = client.post(API + "/buyers", headers=headers,
                    json={"name": name, "buyer_type": "증권사"})
    assert r.status_code == 201, r.text
    return r.json()["buyer_id"]


def _seed_project(client, headers, name, cid, per_years, invoices, sales,
                  approval_status=None, with_payout=True):
    """회계값을 가진 사업 시드 — 차량(캡) + (선택)지급파라미터 + 매입 + 거래계약 목록.

    sales: [{...ProjectSaleIn...}] 그대로 POST. with_payout=False면 예상지급액 None 게이트.
    """
    pid = _mk_project(client, headers, name, approval_status=approval_status)
    for pv in per_years:
        r = client.post(f"{PROJECTS}/{pid}/vehicles", headers=headers,
                        json=_capped_vehicle(pv, cid))
        assert r.status_code == 201, r.text
    if with_payout:
        client.put(f"{PROJECTS}/{pid}/payout-params", headers=headers,
                   json={"max_payment": 1200000, "approved_at": "2016-02-01"})
    for amt in invoices:
        client.post(f"{PROJECTS}/{pid}/purchase-invoices", headers=headers,
                    json={"operator_name": "운수사", "amount": amt})
    for s in sales:
        r = client.post(f"{PROJECTS}/{pid}/sales", headers=headers, json=s)
        assert r.status_code == 201, r.text
    return pid


def _detail(client, headers, pid):
    r = client.get(f"{PROJECTS}/{pid}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _get(client, headers, **params):
    params.setdefault("page_size", 200)
    r = client.get(LEDGER, headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_totals_equal_sum_of_rows(client, staff_headers):
    """총계 == Σ 행(사업 grain 단순합) — sale_recognized·product·gross_profit·inventory."""
    cid = _mk_client(client, staff_headers, "T")
    pa = _seed_project(client, staff_headers, "재무원장TA", cid, [30, 15],
                       [500000, 700000],
                       [{"buyer_name": "증권", "sale_invoice_amount": 3000000,
                         "ownership_pct": 100}])
    pb = _seed_project(client, staff_headers, "재무원장TB", cid, [20],
                       [400000],
                       [{"buyer_name": "증권", "sale_invoice_amount": 2000000,
                         "ownership_pct": 100}])
    body = _get(client, staff_headers, search="재무원장T")
    assert body["total"] == 2
    items = {row["project_id"]: row for row in body["items"]}
    assert set(items) == {pa, pb}

    # 행 == 사업 상세(동일 compute_accounting 원천)
    da = _detail(client, staff_headers, pa)
    dbd = _detail(client, staff_headers, pb)
    for pid, d in ((pa, da), (pb, dbd)):
        for key in ("product", "sale_recognized", "gross_profit", "inventory",
                    "expected_payment", "wip1", "wip2", "liability"):
            assert items[pid][key] == d[key], (pid, key)

    # 총계 == Σ 행(단순합)
    totals = body["totals"]
    for key in ("product", "sale_recognized", "gross_profit", "inventory",
                "expected_payment", "wip1", "wip2", "liability"):
        assert totals[key] == round(items[pa][key] + items[pb][key], 2), key
    # 총이익률 = 총 gross_profit / 총 sale_recognized
    assert totals["profit_rate"] == round(
        totals["gross_profit"] / totals["sale_recognized"], 3
    )
    # 비율은 총계에서 제외(합산 무의미)
    assert "payout_rate" not in totals


def test_none_propagation(client, staff_headers):
    """예상지급액 전건 None → 매출/이익/미착품 None, product는 산출(회계 게이트)."""
    cid = _mk_client(client, staff_headers, "N")
    pid = _seed_project(client, staff_headers, "재무원장NONE", cid, [10],
                        [300000],
                        [{"buyer_name": "증권", "sale_invoice_amount": 1000000,
                          "ownership_pct": 100}],
                        with_payout=False)
    body = _get(client, staff_headers, search="재무원장NONE")
    assert body["total"] == 1
    row = body["items"][0]
    assert row["project_id"] == pid
    assert row["expected_payment"] is None
    assert row["sale_recognized"] is None
    assert row["gross_profit"] is None
    assert row["wip1"] is None
    assert row["inventory"] is None
    assert row["product"] == 300000  # 제품은 단가 무관 산출
    # 총계도 None 전파(전건 None) — product만 합산
    totals = body["totals"]
    assert totals["sale_recognized"] is None
    assert totals["gross_profit"] is None
    assert totals["profit_rate"] is None
    assert totals["product"] == 300000


def test_filters_narrow_and_totals_recompute(client, staff_headers):
    """approval_status·buyer_id·invoice_from/to·is_hold 필터가 행 수 좁힘 + 총계 재계산."""
    cid = _mk_client(client, staff_headers, "F")
    bid_sec = _mk_buyer(client, staff_headers, "재무매수증권F")
    bid_inv = _mk_buyer(client, staff_headers, "재무매수투자F")
    # P1: 승인, 증권 매수, 발행일 2025-03-01, 판매(is_hold N)
    p1 = _seed_project(client, staff_headers, "재무필터F1", cid, [30], [500000],
                       [{"buyer_name": "증권", "buyer_id": bid_sec,
                         "sale_invoice_amount": 3000000, "ownership_pct": 100,
                         "sale_invoice_date": "2025-03-01", "is_hold": "N"}],
                       approval_status="승인")
    # P2: 미승인, 투자 매수, 발행일 2025-06-01, 후시보유(is_hold Y)
    p2 = _seed_project(client, staff_headers, "재무필터F2", cid, [20], [400000],
                       [{"buyer_name": "투자", "buyer_id": bid_inv,
                         "sale_invoice_amount": 2000000, "ownership_pct": 100,
                         "sale_invoice_date": "2025-06-01", "is_hold": "Y"}],
                       approval_status="미승인")

    base = {"search": "재무필터F"}
    assert _get(client, staff_headers, **base)["total"] == 2

    # approval_status
    a = _get(client, staff_headers, **base, approval_status="승인")
    assert [r["project_id"] for r in a["items"]] == [p1]
    assert _get(client, staff_headers, **base, approval_status="미승인")["total"] == 1

    # buyer_id
    b = _get(client, staff_headers, **base, buyer_id=bid_sec)
    assert [r["project_id"] for r in b["items"]] == [p1]
    # 총계 재계산 — 좁힌 결과(P1 단독)와 일치
    assert b["totals"]["product"] == b["items"][0]["product"]

    # invoice_from/to (매출세금계산서 발행일)
    f = _get(client, staff_headers, **base, invoice_from="2025-05-01")
    assert [r["project_id"] for r in f["items"]] == [p2]
    t = _get(client, staff_headers, **base, invoice_to="2025-04-01")
    assert [r["project_id"] for r in t["items"]] == [p1]

    # is_hold(후시보유 계약 보유 사업 = P2)
    h = _get(client, staff_headers, **base, is_hold="Y")
    assert [r["project_id"] for r in h["items"]] == [p2]


def test_distinct_no_duplicate_rows(client, staff_headers):
    """buyer 필터가 EXISTS join을 유발해도(다건 계약) 사업 행은 중복되지 않는다."""
    cid = _mk_client(client, staff_headers, "D")
    bid = _mk_buyer(client, staff_headers, "재무매수중복D")
    pid = _seed_project(client, staff_headers, "재무중복D", cid, [30], [500000],
                        [{"buyer_name": "증권", "buyer_id": bid,
                          "sale_invoice_amount": 1500000, "ownership_pct": 50},
                         {"buyer_name": "증권", "buyer_id": bid,
                          "sale_invoice_amount": 1500000, "ownership_pct": 50}])
    body = _get(client, staff_headers, search="재무중복D", buyer_id=bid)
    assert body["total"] == 1
    assert [r["project_id"] for r in body["items"]] == [pid]


# --- 외부역할 격리(포털) — 내부 조회 라우터는 외부역할이면 403 ---
def _ensure_external_user(user_id, email, role):
    db = models.SessionLocal()
    try:
        u = db.get(models.User, user_id)
        if u is None:
            u = models.User(user_id=user_id, email=email, name=email.split("@")[0])
            db.add(u)
        u.role = role
        u.status = "ACTIVE"
        db.commit()
    finally:
        db.close()


# --- FL-2: 후시/계약 소유권 분할 + 재고평가(오늘 시세) + 현재시세 노출 ---
RATES = API + "/market-rates"


def _split_project(client, headers, name, cid, sales):
    """분할 검증용 최소 사업(차량·지급파라미터·거래계약) — 승인 시드."""
    return _seed_project(client, headers, name, cid, [30], [500000], sales,
                         approval_status="승인")


def test_fl2_no_rate_inventory_none(client, staff_headers):
    """시세 미등록 상태(세션 첫 시세 등록 전) → 현재시세·재고평가 None(후시보유 있어도).

    주의: 이 테스트는 세션 공유 DB에서 어떤 시세도 등록되기 전에 돌아야 유효하므로
    FL-2 블록 최상단(시세 등록 테스트 이전)에 둔다(pytest 정의 순서 보장).
    """
    cid = _mk_client(client, staff_headers, "NORATE")
    pid = _split_project(
        client, staff_headers, "재무무시세N", cid,
        [{"buyer_name": "증권", "sale_invoice_amount": 1000000,
          "quantity": 30, "ownership_pct": 100, "is_hold": "Y"}],
    )
    body = _get(client, staff_headers, search="재무무시세N")
    row = body["items"][0]
    assert row["project_id"] == pid
    assert body["current_market_rate"] is None  # 시세 미등록
    assert row["held_qty"] == 30.0  # 후시보유는 잡히되
    assert row["inventory_valuation"] is None  # 시세 없어 재고평가 None
    assert body["totals"]["inventory_valuation"] is None


def test_ownership_split_and_inventory_valuation(client, staff_headers, admin_headers):
    """후시보유·판매 계약 혼재 → held/sold 분할·재고평가·정합식(held+sold==ownership_total)."""
    # 오늘 기준 현재시세 등록(과거 발효일 → 오늘 이하 최신)
    r = client.post(RATES, headers=admin_headers,
                    json={"effective_date": "2026-01-01", "unit_price": 12000})
    assert r.status_code == 201, r.text

    cid = _mk_client(client, staff_headers, "SPLIT")
    # 후시보유 60(is_hold Y, 소유권 40) + 판매 계약 40(is_hold N, 소유권 60)
    pid = _split_project(
        client, staff_headers, "재무분할S", cid,
        [{"buyer_name": "증권", "sale_invoice_amount": 3000000,
          "quantity": 60, "ownership_pct": 40, "is_hold": "Y"},
         {"buyer_name": "투자", "sale_invoice_amount": 2000000,
          "quantity": 40, "ownership_pct": 60, "is_hold": "N"}],
    )
    body = _get(client, staff_headers, search="재무분할S")
    assert body["total"] == 1
    row = body["items"][0]
    assert row["project_id"] == pid

    # 분할 정확
    assert row["held_qty"] == 60.0
    assert row["sold_qty"] == 40.0
    assert row["held_ownership"] == 40.0
    assert row["sold_ownership"] == 60.0
    # 정합식: held+sold == ownership_total
    assert row["held_ownership"] + row["sold_ownership"] == row["ownership_total"]

    # 재고평가 == round(held_qty × 오늘 시세)
    assert body["current_market_rate"] == 12000.0
    assert row["inventory_valuation"] == round(60.0 * 12000.0)

    # 총계 정합 — held_qty·inventory_valuation == Σ 행
    totals = body["totals"]
    assert totals["held_qty"] == row["held_qty"]
    assert totals["inventory_valuation"] == row["inventory_valuation"]


def test_inventory_valuation_none_when_no_hold(client, staff_headers, admin_headers):
    """후시보유 없음(전량 판매 계약) → 시세가 있어도 held_qty 0이라 재고평가 None."""
    client.post(RATES, headers=admin_headers,
                json={"effective_date": "2026-01-01", "unit_price": 11000})
    cid = _mk_client(client, staff_headers, "NOHOLD")
    pid = _split_project(
        client, staff_headers, "재무무재고N", cid,
        [{"buyer_name": "증권", "sale_invoice_amount": 1000000,
          "quantity": 50, "ownership_pct": 100, "is_hold": "N"}],
    )
    body = _get(client, staff_headers, search="재무무재고N")
    row = body["items"][0]
    assert row["project_id"] == pid
    assert body["current_market_rate"] is not None  # 시세는 존재
    assert row["held_qty"] == 0.0  # 후시보유 없음
    assert row["inventory_valuation"] is None  # held 0 → 재고평가 None


def test_split_is_read_only(client, staff_headers, admin_headers):
    """분할·재고평가는 비영속 — 응답 후 ProjectSale 레코드 불변."""
    client.post(RATES, headers=admin_headers,
                json={"effective_date": "2026-01-01", "unit_price": 10000})
    cid = _mk_client(client, staff_headers, "RO")
    pid = _split_project(
        client, staff_headers, "재무불변RO", cid,
        [{"buyer_name": "증권", "sale_invoice_amount": 1000000,
          "quantity": 20, "ownership_pct": 100, "is_hold": "Y"}],
    )
    before = _detail(client, staff_headers, pid)["sales"]
    _get(client, staff_headers, search="재무불변RO")
    after = _detail(client, staff_headers, pid)["sales"]
    assert before == after  # 응답 조립이 계약 레코드를 바꾸지 않음


def test_external_role_blocked(client):
    _ensure_external_user("u-fl-partner", "fl-partner@carrier.example", "PARTNER")
    tok = client.post("/api/v1/auth/dev-login", json={"email": "fl-partner@carrier.example"})
    assert tok.status_code == 200, tok.text
    headers = {"Authorization": "Bearer {0}".format(tok.json()["access_token"])}
    r = client.get(LEDGER, headers=headers)
    assert r.status_code == 403, r.text  # 포털 격리
