"""외부 사용자 신원(/portal/me) + 외부 열람 감사(PORTAL_VIEW) (Phase 4 INC-7a).

- /portal/me: 로그인한 외부계정의 역할·소속(org_name)을 반환. 내부역할 403·미인증 401(격리).
- 상세 열람 시 AuditLog에 PORTAL_VIEW 1건(actor=외부계정, target=project)이 남는지 DB로 확인.
  금액/감축량 값은 기록하지 않는다(R2-E6, new_value=role만).
"""

import pytest

import models
from auth import create_access_token

API = "/api/v1"
PORTAL = API + "/portal"
PROJECTS = API + "/projects"


# ---------------------------------------------------------------------------
# 마스터/프로젝트 생성 헬퍼 (test_portal_endpoints와 동일 관용구 — 내부 STAFF API 재사용)
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
    p = {"registered_at": "2016-01-01", "client_id": client_id}
    for i in range(1, 9):
        p[f"reduction_y{i}"] = per_year
    return p


def _external_user(user_id, email, role, **extra):
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


@pytest.fixture(scope="module")
def me_data(client, staff_headers):
    ca = _mk_client(client, staff_headers, "미신원운수사갑")
    bx = _mk_buyer(client, staff_headers, "미신원투자엑스")

    p1 = _mk_project(client, staff_headers, "미신원P1")
    client.post(f"{PROJECTS}/{p1}/vehicles", headers=staff_headers, json=_capped_vehicle(ca, 30))
    client.post(
        f"{PROJECTS}/{p1}/sales",
        headers=staff_headers,
        json={"buyer_name": "미신원투자엑스", "buyer_id": bx, "sale_invoice_amount": 3000000,
              "sale_unit_price": 15000, "quantity": 200, "ownership_pct": 100},
    )

    partner = _external_user("u-me-partner", "partner@me.example", "PARTNER", client_id=ca)
    investor = _external_user("u-me-investor", "investor@me.example", "INVESTOR", buyer_id=bx)
    return {"p1": p1, "ca": ca, "bx": bx, "partner": partner, "investor": investor}


# ---------------------------------------------------------------------------
# 1. /portal/me — 신원·소속
# ---------------------------------------------------------------------------
def test_portal_me_partner(client, me_data):
    r = client.get(f"{PORTAL}/me", headers=_headers(me_data["partner"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == "u-me-partner"
    assert body["role"] == "PARTNER"
    assert body["org_name"] == "미신원운수사갑"


def test_portal_me_investor(client, me_data):
    r = client.get(f"{PORTAL}/me", headers=_headers(me_data["investor"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "INVESTOR"
    assert body["org_name"] == "미신원투자엑스"


def test_portal_me_internal_role_403(client, staff_headers):
    """내부 STAFF 토큰 → 403(require_external_role 격리)."""
    r = client.get(f"{PORTAL}/me", headers=staff_headers)
    assert r.status_code == 403, r.text


def test_portal_me_unauthenticated_401(client):
    r = client.get(f"{PORTAL}/me")
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# 2. 상세 열람 감사(PORTAL_VIEW) — DB로 확인
# ---------------------------------------------------------------------------
def test_portal_view_audited(client, me_data):
    r = client.get(f"{PORTAL}/projects/{me_data['p1']}", headers=_headers(me_data["partner"]))
    assert r.status_code == 200, r.text

    db = models.SessionLocal()
    try:
        rows = (
            db.query(models.AuditLog)
            .filter(
                models.AuditLog.action == "PORTAL_VIEW",
                models.AuditLog.target_id == me_data["p1"],
                models.AuditLog.actor_id == "u-me-partner",
            )
            .all()
        )
    finally:
        db.close()
    assert len(rows) == 1, rows
    log = rows[0]
    assert log.target_type == "PROJECT"
    assert log.new_value == "PARTNER"  # role만 기록(금액/감축량 값 없음)
