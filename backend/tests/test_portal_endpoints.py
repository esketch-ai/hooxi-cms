"""포털 조회 엔드포인트 + 매직링크 인증 + 스코프 (Phase 4 INC-5 / 부록 N.8 D2).

핵심:
- 매직링크: magic 토큰 verify → access+refresh 발급. 만료/무효 401, 내부역할 403.
- 스코프: PARTNER는 자기 참여 프로젝트만, INVESTOR는 자기 거래 프로젝트만.
  스코프 밖 상세는 존재 여부를 노출하지 않고 404.
- 격리(D3): 내부역할은 /portal에서 403, 외부역할은 내부 /projects에서 403(회귀 확인).

인증 경로: (a) create_magic_token→/portal/auth/verify→access 획득 1건 검증,
(b) 나머지는 create_access_token(user) 직접 사용.
"""

from datetime import timedelta

import pytest

import models
from auth import (
    _create_token,
    create_access_token,
    create_magic_token,
)

API = "/api/v1"
PORTAL = API + "/portal"
PROJECTS = API + "/projects"


# ---------------------------------------------------------------------------
# 마스터/프로젝트 생성 헬퍼 (내부 STAFF API 재사용 — test_portal_views와 동일 관용구)
# ---------------------------------------------------------------------------
def _mk_project(client, headers, name):
    r = client.post(PROJECTS, headers=headers, json={"project_name": name, "project_status": "기획"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def _mk_client(client, headers, name):
    r = client.post(API + "/clients", headers=headers, json={"client_type": "TRANSPORT", "company_name": name})
    assert r.status_code == 201, r.text
    return r.json()["client_id"]


def _mk_buyer(client, headers, name):
    r = client.post(API + "/buyers", headers=headers, json={"name": name, "buyer_type": "투자사"})
    assert r.status_code == 201, r.text
    return r.json()["buyer_id"]


def _capped_vehicle(client_id, per_year):
    """잔여차령 8 캡 노후차 — y1..y8 동일값(잔여반영=Σ). 등록 2016-01-01, 운수사 지정."""
    p = {"registered_at": "2016-01-01", "client_id": client_id}
    for i in range(1, 9):
        p[f"reduction_y{i}"] = per_year
    return p


def _external_user(user_id, email, role, **extra):
    """외부역할 ACTIVE 계정 생성/갱신 (test_external_isolation과 동일 관용구)."""
    db = models.SessionLocal()
    try:
        u = db.get(models.User, user_id)
        if u is None:
            u = models.User(user_id=user_id, email=email, name=email.split("@")[0])
            db.add(u)
        u.role = role
        u.status = "ACTIVE"
        for k, v in extra.items():
            setattr(u, k, v)
        db.commit()
        db.refresh(u)
        db.expunge(u)
        return u
    finally:
        db.close()


def _headers(user):
    return {"Authorization": "Bearer {0}".format(create_access_token(user))}


# ---------------------------------------------------------------------------
# 공용 데이터: P1(A·B 차량 + X 계약), P2(B 차량 + Y 계약)
#   → PARTNER A는 P1만, INVESTOR X는 P1만 스코프. P2는 각각 스코프 밖(404 대상).
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def portal_data(client, staff_headers):
    ca = _mk_client(client, staff_headers, "포털운수사갑")
    cb = _mk_client(client, staff_headers, "포털운수사을")
    bx = _mk_buyer(client, staff_headers, "포털투자엑스")
    by = _mk_buyer(client, staff_headers, "포털투자와이")

    # P1: A(30)+A(15)+B(10), payout-params, 매수자 X 실발행 3,000,000
    p1 = _mk_project(client, staff_headers, "포털P1")
    client.post(f"{PROJECTS}/{p1}/vehicles", headers=staff_headers, json=_capped_vehicle(ca, 30))
    client.post(f"{PROJECTS}/{p1}/vehicles", headers=staff_headers, json=_capped_vehicle(ca, 15))
    client.post(f"{PROJECTS}/{p1}/vehicles", headers=staff_headers, json=_capped_vehicle(cb, 10))
    client.put(
        f"{PROJECTS}/{p1}/payout-params",
        headers=staff_headers,
        json={"max_payment": 1200000, "approved_at": "2016-02-01"},
    )
    client.post(
        f"{PROJECTS}/{p1}/sales",
        headers=staff_headers,
        json={"buyer_name": "포털투자엑스", "buyer_id": bx, "sale_invoice_amount": 3000000,
              "sale_unit_price": 15000, "quantity": 200, "ownership_pct": 100},
    )

    # P2: B(20) 차량, 매수자 Y 계약 — A·X 스코프 밖
    p2 = _mk_project(client, staff_headers, "포털P2")
    client.post(f"{PROJECTS}/{p2}/vehicles", headers=staff_headers, json=_capped_vehicle(cb, 20))
    client.post(
        f"{PROJECTS}/{p2}/sales",
        headers=staff_headers,
        json={"buyer_name": "포털투자와이", "buyer_id": by, "sale_invoice_amount": 1000000, "ownership_pct": 100},
    )

    partner = _external_user("u-portal-partner", "partner@portal.example", "PARTNER", client_id=ca)
    investor = _external_user("u-portal-investor", "investor@portal.example", "INVESTOR", buyer_id=bx)
    return {"p1": p1, "p2": p2, "partner": partner, "investor": investor}


# ---------------------------------------------------------------------------
# 1. 매직링크 인증
# ---------------------------------------------------------------------------
def test_magic_verify_issues_token_pair(client, portal_data):
    """(a) magic 토큰 verify → access+refresh 발급, 그 access로 /portal/projects 통과."""
    token = create_magic_token(portal_data["partner"])
    r = client.post(f"{PORTAL}/auth/verify", json={"token": token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["token_type"] == "bearer"
    # user 정보는 노출하지 않는다(TokenPair)
    assert "user" not in body

    # 발급된 access로 실제 조회 통과
    r2 = client.get(
        f"{PORTAL}/projects",
        headers={"Authorization": "Bearer {0}".format(body["access_token"])},
    )
    assert r2.status_code == 200, r2.text


def test_magic_verify_rejects_expired(client, portal_data):
    expired = _create_token(portal_data["partner"], "magic", timedelta(seconds=-1))
    r = client.post(f"{PORTAL}/auth/verify", json={"token": expired})
    assert r.status_code == 401, r.text


def test_magic_verify_rejects_invalid(client):
    r = client.post(f"{PORTAL}/auth/verify", json={"token": "not-a-real-token"})
    assert r.status_code == 401, r.text


def test_magic_verify_rejects_internal_role(client):
    """내부 STAFF의 magic 토큰은 verify에서 403(외부역할만)."""
    db = models.SessionLocal()
    try:
        staff = db.get(models.User, "u-staff")
        token = create_magic_token(staff)
    finally:
        db.close()
    r = client.post(f"{PORTAL}/auth/verify", json={"token": token})
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 2. PARTNER 스코프
# ---------------------------------------------------------------------------
def test_partner_projects_self_only(client, portal_data):
    r = client.get(f"{PORTAL}/projects", headers=_headers(portal_data["partner"]))
    assert r.status_code == 200, r.text
    ids = {p["project_id"] for p in r.json()}
    assert portal_data["p1"] in ids       # 자기 참여
    assert portal_data["p2"] not in ids    # 타 운수사(B)만 참여 → 미포함


def test_partner_project_detail_view(client, portal_data):
    r = client.get(f"{PORTAL}/projects/{portal_data['p1']}", headers=_headers(portal_data["partner"]))
    assert r.status_code == 200, r.text
    view = r.json()
    assert view["my_vehicle_count"] == 2          # A 차량만(B 미포함)
    assert view["my_effective_reduction"] == 360  # 240 + 120
    assert view["my_expected_payout"] == 1800000  # 자기 수혜금액
    # 매출/원가율 키 부재(원천 미포함)
    for forbidden in ("total_contract_revenue", "my_contract", "sale_unit_price", "payout_rate"):
        assert forbidden not in view


def test_partner_project_out_of_scope_404(client, portal_data):
    r = client.get(f"{PORTAL}/projects/{portal_data['p2']}", headers=_headers(portal_data["partner"]))
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# 3. INVESTOR 스코프
# ---------------------------------------------------------------------------
def test_investor_projects_self_only(client, portal_data):
    r = client.get(f"{PORTAL}/projects", headers=_headers(portal_data["investor"]))
    assert r.status_code == 200, r.text
    ids = {p["project_id"] for p in r.json()}
    assert portal_data["p1"] in ids       # 자기 거래(X)
    assert portal_data["p2"] not in ids    # 타 매수자(Y)만 거래 → 미포함


def test_investor_project_detail_view(client, portal_data):
    r = client.get(f"{PORTAL}/projects/{portal_data['p1']}", headers=_headers(portal_data["investor"]))
    assert r.status_code == 200, r.text
    view = r.json()
    # 운수사별 감축량(익명 라벨) + 총매출
    labels = [o["label"] for o in view["operators_reduction"]]
    assert labels == ["운수사 1", "운수사 2"]
    assert "갑" not in " ".join(labels) and "을" not in " ".join(labels)
    assert view["total_effective_reduction"] == 440
    assert view["total_contract_revenue"] == 3000000
    # 예상지급액/지급률 키 부재
    for forbidden in ("my_expected_payout", "expected_payment", "payout_rate", "product"):
        assert forbidden not in view


def test_investor_project_out_of_scope_404(client, portal_data):
    r = client.get(f"{PORTAL}/projects/{portal_data['p2']}", headers=_headers(portal_data["investor"]))
    assert r.status_code == 404, r.text


def test_portal_projects_empty_when_no_scope(client):
    """client_id/buyer_id 미설정 외부계정은 빈 목록."""
    unscoped = _external_user("u-portal-unscoped", "unscoped@portal.example", "PARTNER")
    r = client.get(f"{PORTAL}/projects", headers=_headers(unscoped))
    assert r.status_code == 200, r.text
    assert r.json() == []


# ---------------------------------------------------------------------------
# 4. 격리(D3) — 양방향
# ---------------------------------------------------------------------------
def test_internal_role_blocked_on_portal(client, staff_headers):
    """내부 STAFF 토큰으로 /portal/projects → 403(require_external_role)."""
    r = client.get(f"{PORTAL}/projects", headers=staff_headers)
    assert r.status_code == 403, r.text


def test_external_role_blocked_on_internal(client, portal_data):
    """외부 토큰으로 내부 /projects → 403(회귀 확인)."""
    r = client.get(PROJECTS, headers=_headers(portal_data["partner"]))
    assert r.status_code == 403, r.text
