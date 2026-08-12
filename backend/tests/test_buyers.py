"""매수자 마스터(tb_buyer) — CRUD·SALE_BUYER_TYPE 재사용·거래계약 buyer_id 연동.

전환기: ProjectSale.buyer_name(free-text)은 유지하고 buyer_id FK로 마스터를 참조한다.
(SQLite는 FK ondelete SET NULL을 강제하지 않으므로, 삭제 시 거래계약 보존만 API 레벨로 검증.)
"""

API = "/api/v1"
BUYERS = API + "/buyers"
PROJECTS = API + "/projects"


def _mk_project(client, headers, name):
    r = client.post(PROJECTS, headers=headers, json={"project_name": name, "project_status": "기획"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def test_buyer_type_uses_sale_buyer_type_codes(client, staff_headers):
    """매수자 구분은 기존 SALE_BUYER_TYPE 공통코드 재사용(별도 카테고리 신설 없음)."""
    r = client.get(API + "/codes", headers=staff_headers, params={"category": "SALE_BUYER_TYPE"})
    assert r.status_code == 200, r.text
    codes = {c["code"] for c in r.json()}
    assert {"증권사", "투자사", "금융사"} <= codes


def test_buyer_crud(client, staff_headers):
    r = client.post(
        BUYERS,
        headers=staff_headers,
        json={"name": "한국증권", "buyer_type": "증권사", "contact_name": "홍길동"},
    )
    assert r.status_code == 201, r.text
    bid = r.json()["buyer_id"]
    assert r.json()["name"] == "한국증권"

    # 상세
    assert client.get(f"{BUYERS}/{bid}", headers=staff_headers).json()["contact_name"] == "홍길동"

    # 검색 목록 — name ilike
    lr = client.get(BUYERS, headers=staff_headers, params={"q": "한국"}).json()
    assert lr["total"] >= 1
    assert any(b["buyer_id"] == bid for b in lr["items"])

    # 수정
    u = client.put(f"{BUYERS}/{bid}", headers=staff_headers, json={"memo": "우선 매수자"})
    assert u.status_code == 200, u.text
    assert u.json()["memo"] == "우선 매수자"
    assert u.json()["name"] == "한국증권"  # 미전달 필드 보존

    # 삭제
    assert client.delete(f"{BUYERS}/{bid}", headers=staff_headers).status_code == 200
    assert client.get(f"{BUYERS}/{bid}", headers=staff_headers).status_code == 404


def test_buyer_name_duplicate_409(client, staff_headers):
    client.post(BUYERS, headers=staff_headers, json={"name": "중복매수자"})
    r = client.post(BUYERS, headers=staff_headers, json={"name": "중복매수자"})
    assert r.status_code == 409, r.text


def test_buyer_invalid_type_422(client, staff_headers):
    r = client.post(BUYERS, headers=staff_headers, json={"name": "구분오류사", "buyer_type": "없는구분"})
    assert r.status_code == 422, r.text


def test_sale_links_buyer_id_and_syncs_name(client, staff_headers):
    """거래계약에 buyer_id 연결 — 존재 검증 통과 시 buyer_name을 마스터명으로 동기화."""
    b = client.post(BUYERS, headers=staff_headers, json={"name": "연동증권"}).json()
    pid = _mk_project(client, staff_headers, "매수자연동검증")
    r = client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "구표기", "buyer_id": b["buyer_id"], "sale_unit_price": 15000},
    )
    assert r.status_code == 201, r.text
    assert r.json()["buyer_id"] == b["buyer_id"]
    assert r.json()["buyer_name"] == "연동증권"  # 마스터명으로 동기화


def test_sale_unknown_buyer_id_404(client, staff_headers):
    pid = _mk_project(client, staff_headers, "매수자없음검증")
    r = client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "X", "buyer_id": "no-such-buyer"},
    )
    assert r.status_code == 404, r.text


def test_delete_buyer_preserves_sale(client, staff_headers):
    """매수자 삭제 시 거래계약 자체는 보존(FK ondelete SET NULL). API 레벨: 삭제 200·계약 잔존."""
    b = client.post(BUYERS, headers=staff_headers, json={"name": "삭제대상증권"}).json()
    pid = _mk_project(client, staff_headers, "매수자삭제보존검증")
    client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "삭제대상증권", "buyer_id": b["buyer_id"]},
    )
    assert client.delete(f"{BUYERS}/{b['buyer_id']}", headers=staff_headers).status_code == 200
    # 거래계약은 그대로 남는다(계약 보존)
    assert client.get(f"{PROJECTS}/{pid}/sales", headers=staff_headers).json()["total"] == 1


def test_delete_buyer_blocked_by_active_investor_account(client, staff_headers):
    """활성 INVESTOR 외부 포털 계정이 연결된 매수자는 삭제 차단(409) — 스코프 조용한 단절 방지.

    비활성(INACTIVE) 계정은 차단 대상이 아니어야 한다(삭제 허용).
    """
    import models

    b = client.post(BUYERS, headers=staff_headers, json={"name": "포털연결증권"}).json()
    bid = b["buyer_id"]

    # 활성 INVESTOR 계정 연결 → 삭제 409
    db = models.SessionLocal()
    try:
        db.add(models.User(
            user_id="inv-del-guard", email="inv-del@buyer.example", name="투자사",
            role="INVESTOR", status="ACTIVE", buyer_id=bid,
        ))
        db.commit()
    finally:
        db.close()
    r = client.delete(f"{BUYERS}/{bid}", headers=staff_headers)
    assert r.status_code == 409, r.text

    # 계정 비활성화 후에는 삭제 허용(200)
    db = models.SessionLocal()
    try:
        u = db.get(models.User, "inv-del-guard")
        u.status = "INACTIVE"
        db.commit()
    finally:
        db.close()
    assert client.delete(f"{BUYERS}/{bid}", headers=staff_headers).status_code == 200
