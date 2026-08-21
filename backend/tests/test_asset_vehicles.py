"""자산관리 > 전기버스 — 크로스-프로젝트 차량 뷰(AV-1).

여러 사업을 가로질러 차량을 한 목록으로 나열하는 내부 전용 조회 + 차량 KPI 검증.
- 크로스-프로젝트 혼합, 각 필터 좁힘, 통합검색(차량번호·운수사명), KPI 합, 페이지 경계, 외부역할 403.
"""

import models

API = "/api/v1"
PROJECTS = API + "/projects"
ASSET_VEHICLES = API + "/asset-vehicles"


def _mk_project(client, headers, name, approval_status=None):
    body = {"project_name": name, "project_status": "기획"}
    if approval_status:
        body["approval_status"] = approval_status
    r = client.post(PROJECTS, headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def _add_vehicle(client, headers, pid, **fields):
    r = client.post(f"{PROJECTS}/{pid}/vehicles", headers=headers, json=fields)
    assert r.status_code == 201, r.text
    return r.json()["vehicle_id"]


def _seed(client, headers, tag):
    """운수사 1곳을 P1·P2 양쪽 차량에 배정해 크로스-프로젝트 격자를 만든다.

    tag로 운수사명·차량번호·매수자명을 유니크하게 해 테스트 간 격리(유니크 제약·검색 충돌 회피).
    """
    cr = client.post(
        API + "/clients", headers=headers,
        json={"client_type": "TRANSPORT", "company_name": "크로스운수" + tag},
    )
    assert cr.status_code == 201, cr.text
    cid = cr.json()["client_id"]
    p1 = _mk_project(client, headers, "크로스차량뷰P1" + tag, approval_status="승인")
    p2 = _mk_project(client, headers, "크로스차량뷰P2" + tag, approval_status="미승인")
    # P1: 제주 2대(2020 등록), P2: 서울 1대(2022 등록)
    v1 = _add_vehicle(client, headers, p1, vehicle_no="제주79자" + tag + "1", region="제주",
                      client_id=cid, registered_at="2020-01-01", reduction_y1=10)
    v2 = _add_vehicle(client, headers, p1, vehicle_no="제주79자" + tag + "2", region="제주",
                      client_id=cid, registered_at="2020-01-01", reduction_y1=20)
    v3 = _add_vehicle(client, headers, p2, vehicle_no="서울70바" + tag, region="서울",
                      client_id=cid, registered_at="2022-06-01", reduction_y1=5)
    # 매수자 + P1 거래계약(buyer_id 필터용)
    bname = "크로스매수" + tag
    bid = client.post(
        API + "/buyers", headers=headers,
        json={"name": bname, "buyer_type": "증권사"},
    ).json()["buyer_id"]
    client.post(f"{PROJECTS}/{p1}/sales", headers=headers,
                json={"buyer_name": bname, "buyer_id": bid})
    return {"cid": cid, "p1": p1, "p2": p2, "v1": v1, "v2": v2, "v3": v3,
            "bid": bid, "cname": "크로스운수" + tag, "v3_no": "서울70바" + tag}


def _get(client, headers, **params):
    r = client.get(ASSET_VEHICLES, headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


# --- AV-2 재무 회계(compute_accounting 재사용) 시드 헬퍼 ---
def _capped_vehicle(per_year, cid):
    """잔여차령 8 캡 노후차(등록 2016-01-01, y1..y8 동일값) — client_id 배정."""
    p = {"registered_at": "2016-01-01", "client_id": cid}
    for i in range(1, 9):
        p["reduction_y{0}".format(i)] = per_year
    return p


def _project_detail(client, headers, pid):
    r = client.get(f"{PROJECTS}/{pid}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _seed_acct_project(client, headers, name, cid, per_years, invoices, sale_amt):
    """회계값을 가진 사업 시드 — 차량(캡) + 지급파라미터 + 매입세금계산서 + 거래계약."""
    pid = _mk_project(client, headers, name)
    for pv in per_years:
        r = client.post(f"{PROJECTS}/{pid}/vehicles", headers=headers,
                        json=_capped_vehicle(pv, cid))
        assert r.status_code == 201, r.text
    client.put(f"{PROJECTS}/{pid}/payout-params", headers=headers,
               json={"max_payment": 1200000, "approved_at": "2016-02-01"})
    for amt in invoices:
        client.post(f"{PROJECTS}/{pid}/purchase-invoices", headers=headers,
                    json={"operator_name": "운수사", "amount": amt})
    if sale_amt is not None:
        client.post(f"{PROJECTS}/{pid}/sales", headers=headers,
                    json={"buyer_name": "증권", "sale_invoice_amount": sale_amt,
                          "ownership_pct": 100})
    return pid


def _mk_client(client, headers, tag):
    r = client.post(API + "/clients", headers=headers,
                    json={"client_type": "TRANSPORT", "company_name": "회계운수" + tag})
    assert r.status_code == 201, r.text
    return r.json()["client_id"]


def test_financial_kpi_and_row_accounting(client, staff_headers):
    """재무 KPI = distinct 사업 회계 합, 행별 project_revenue/cost = 그 사업 회계값(D1-A·D2)."""
    cid = _mk_client(client, staff_headers, "K")
    pa = _seed_acct_project(client, staff_headers, "AV회계P1K", cid, [30, 15],
                            [500000, 700000], 3000000)
    pb = _seed_acct_project(client, staff_headers, "AV회계P2K", cid, [20],
                            [400000], 2000000)
    da = _project_detail(client, staff_headers, pa)
    dbd = _project_detail(client, staff_headers, pb)

    body = _get(client, staff_headers, client_id=cid)
    kpi = body["kpi"]
    # 재무 KPI = 필터된 distinct 사업들의 compute_accounting 합
    assert kpi["revenue"] == da["sale_recognized"] + dbd["sale_recognized"]
    assert kpi["cost"] == da["product"] + dbd["product"]
    assert kpi["profit"] == da["gross_profit"] + dbd["gross_profit"]
    # 차량 KPI와 그레인 무관하게 공존
    assert kpi["vehicle_count"] == 3

    # 행별 사업 회계값 — 같은 사업 차량은 동일값
    for row in body["items"]:
        if row["project_id"] == pa:
            assert row["project_revenue"] == da["sale_recognized"]
            assert row["project_cost"] == da["product"]
        elif row["project_id"] == pb:
            assert row["project_revenue"] == dbd["sale_recognized"]
            assert row["project_cost"] == dbd["product"]

    # 부분집합 과대계상 없음 — 한 사업만 필터하면 그 사업 회계값과 일치
    only_a = _get(client, staff_headers, client_id=cid, project_id=pa)["kpi"]
    assert only_a["revenue"] == da["sale_recognized"]
    assert only_a["cost"] == da["product"]
    assert only_a["profit"] == da["gross_profit"]


def test_financial_kpi_none_propagation(client, staff_headers):
    """예상지급액 전건 None → 회계 게이트: revenue/profit None 전파, cost(제품)는 산출."""
    cid = _mk_client(client, staff_headers, "N")
    pid = _mk_project(client, staff_headers, "AV게이트PN")
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers,
                json={"reduction_y1": 10, "client_id": cid})
    client.post(f"{PROJECTS}/{pid}/purchase-invoices", headers=staff_headers,
                json={"operator_name": "운수사", "amount": 300000})
    body = _get(client, staff_headers, client_id=cid, project_id=pid)
    assert body["kpi"]["revenue"] is None
    assert body["kpi"]["profit"] is None
    assert body["kpi"]["cost"] == 300000  # 제품은 단가 무관 산출
    assert body["items"][0]["project_revenue"] is None
    assert body["items"][0]["project_cost"] == 300000


def test_cross_project_mix(client, staff_headers):
    s = _seed(client, staff_headers, "A")
    body = _get(client, staff_headers, client_id=s["cid"])
    assert body["total"] == 3
    # 두 사업의 차량이 한 목록에 혼합
    pids = {row["project_id"] for row in body["items"]}
    assert pids == {s["p1"], s["p2"]}
    vids = {row["vehicle_id"] for row in body["items"]}
    assert vids == {s["v1"], s["v2"], s["v3"]}


def test_filters_narrow(client, staff_headers):
    s = _seed(client, staff_headers, "B")
    base = {"client_id": s["cid"]}

    # project_id
    assert _get(client, staff_headers, **base, project_id=s["p1"])["total"] == 2
    # region
    assert _get(client, staff_headers, **base, region="제주")["total"] == 2
    assert _get(client, staff_headers, **base, region="서울")["total"] == 1
    # approval_status(Project)
    assert _get(client, staff_headers, **base, approval_status="승인")["total"] == 2
    assert _get(client, staff_headers, **base, approval_status="미승인")["total"] == 1
    # buyer_id(거래계약 보유 사업 = P1)
    assert _get(client, staff_headers, **base, buyer_id=s["bid"])["total"] == 2
    # registered_from / registered_to
    assert _get(client, staff_headers, **base, registered_from="2021-01-01")["total"] == 1  # P2 2022
    assert _get(client, staff_headers, **base, registered_to="2021-01-01")["total"] == 2  # P1 2020
    # expire_before — P1(2020 등록) 만료 2028-12-31 <= 2029-06-01, P2 만료 2031 제외
    assert _get(client, staff_headers, **base, expire_before="2029-06-01")["total"] == 2


def test_client_none_filter(client, staff_headers):
    s = _seed(client, staff_headers, "C")
    # 미지정(client_id NULL) 차량 1대 추가 후 __none__ 센티널이 미지정만 잡는지
    _add_vehicle(client, staff_headers, s["p1"], vehicle_no="미지정차C", reduction_y1=1)
    none_rows = _get(client, staff_headers, project_id=s["p1"], client_id="__none__")
    assert all(row["client_id"] is None for row in none_rows["items"])
    assert none_rows["total"] == 1  # P1의 미지정 1대만(배정 2대 제외)


def test_search_matches_vehicle_no_and_client_name(client, staff_headers):
    s = _seed(client, staff_headers, "D")
    # 차량번호 매칭
    by_no = _get(client, staff_headers, search=s["v3_no"])
    assert by_no["total"] == 1
    assert by_no["items"][0]["vehicle_id"] == s["v3"]
    # 운수사명 매칭 → 해당 운수사 3대 모두
    by_name = _get(client, staff_headers, search=s["cname"])
    assert by_name["total"] == 3


def test_kpi_matches_filtered(client, staff_headers):
    s = _seed(client, staff_headers, "E")
    body = _get(client, staff_headers, client_id=s["cid"])
    kpi = body["kpi"]
    assert kpi["vehicle_count"] == 3
    assert kpi["total_reduction"] == 35  # 10 + 20 + 5
    # region으로 좁히면 KPI도 함께 좁혀짐
    jeju = _get(client, staff_headers, client_id=s["cid"], region="제주")
    assert jeju["kpi"]["vehicle_count"] == 2
    assert jeju["kpi"]["total_reduction"] == 30  # 10 + 20


def test_pagination_tiebreak_no_gap(client, staff_headers):
    s = _seed(client, staff_headers, "F")
    p1 = _get(client, staff_headers, client_id=s["cid"], page=1, page_size=2)
    p2 = _get(client, staff_headers, client_id=s["cid"], page=2, page_size=2)
    assert p1["total"] == 3
    assert len(p1["items"]) == 2 and len(p2["items"]) == 1
    ids = {r["vehicle_id"] for r in p1["items"]} | {r["vehicle_id"] for r in p2["items"]}
    assert ids == {s["v1"], s["v2"], s["v3"]}  # 경계 누락/중복 없음


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


def test_external_role_blocked(client):
    _ensure_external_user("u-av-partner", "av-partner@carrier.example", "PARTNER")
    from auth import create_access_token

    db = models.SessionLocal()
    try:
        u = db.query(models.User).filter(models.User.email == "av-partner@carrier.example").first()
        headers = {"Authorization": "Bearer {0}".format(create_access_token(u))}
    finally:
        db.close()
    r = client.get(ASSET_VEHICLES, headers=headers)
    assert r.status_code == 403, r.text  # 포털 격리
