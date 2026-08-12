"""외부역할(PARTNER/INVESTOR) 격리 불변식 — 부록 N.8 D3, Phase 4 INC-2.

핵심 불변식: 외부역할은 내부 라우터에서 자동 403(마스킹 아님, 원천 차단).
- ROLE_LEVEL/PERMISSION_MATRIX에 외부역할이 없으므로 require_role/require_permission이
  미등록 역할을 0/거부 처리 → 코드 변경 없이 전수 거부.

주의(격리 범위): 내부 라우터 중 `Depends(get_current_user)`만 건 조회 엔드포인트
(GET /projects·/clients·/buyers 등)는 role 판정을 하지 않아 ACTIVE 외부계정이면
현재 통과한다. 이는 require_role/require_permission 기반 격리의 사각지대로, 아래
xfail 테스트로 의도(=403이어야 함)를 명시해 후속 증분에서 다루도록 남긴다.
"""

import pytest
from fastapi import Depends, HTTPException

import models
from auth import (
    EXTERNAL_ROLES,
    require_external_role,
    require_permission,
    require_role,
)


# ---------------------------------------------------------------------------
# 외부역할 ACTIVE 계정 직접 생성 + dev-login 토큰 발급 헬퍼
# (conftest의 내부계정 시드/dev-login 방식과 동일 — role만 외부역할)
# ---------------------------------------------------------------------------
def _ensure_external_user(user_id, email, role, **extra):
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
    finally:
        db.close()


def _login(client, email):
    resp = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert resp.status_code == 200, resp.text
    return {"Authorization": "Bearer {0}".format(resp.json()["access_token"])}


@pytest.fixture(scope="module")
def partner_headers(client):
    _ensure_external_user("u-partner", "partner@carrier.example", "PARTNER")
    return _login(client, "partner@carrier.example")


@pytest.fixture(scope="module")
def investor_headers(client):
    _ensure_external_user("u-investor", "investor@buyer.example", "INVESTOR")
    return _login(client, "investor@buyer.example")


# ---------------------------------------------------------------------------
# 1. 내부 라우터 전수 403 — require_role/require_permission 기반 엔드포인트
# ---------------------------------------------------------------------------
# GET(require_role/permission) — 외부역할이면 403이어야 하는 조회 엔드포인트
_GUARDED_GET = [
    "/api/v1/users",  # require_role("MANAGER")
]
# 쓰기(require_permission("master.write")/("client.delete")) — 외부역할이면 403
_GUARDED_POST = [
    ("/api/v1/clients", {}),
    ("/api/v1/buyers", {}),
    ("/api/v1/projects", {}),
]


@pytest.mark.parametrize("path", _GUARDED_GET)
def test_partner_blocked_on_guarded_get(client, partner_headers, path):
    r = client.get(path, headers=partner_headers)
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("path", _GUARDED_GET)
def test_investor_blocked_on_guarded_get(client, investor_headers, path):
    r = client.get(path, headers=investor_headers)
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("path,body", _GUARDED_POST)
def test_partner_blocked_on_guarded_write(client, partner_headers, path, body):
    # require_permission 의존성이 body 검증(422)보다 먼저 거부 → 403
    r = client.post(path, headers=partner_headers, json=body)
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("path,body", _GUARDED_POST)
def test_investor_blocked_on_guarded_write(client, investor_headers, path, body):
    r = client.post(path, headers=investor_headers, json=body)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 2. 내부 STAFF 회귀 없음 — 기존대로 조회 동작
# ---------------------------------------------------------------------------
def test_internal_staff_still_works(client, staff_headers):
    # STAFF는 get_current_user 기반 조회가 정상 동작(200)해야 한다(회귀 없음).
    r = client.get("/api/v1/projects", headers=staff_headers)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# 3. require_external_role 의존성 단위 검증 (get_current_user 우회 — 직접 호출)
# ---------------------------------------------------------------------------
def _fake_user(role):
    return models.User(user_id="x", email="x@x", name="x", role=role, status="ACTIVE")


def test_require_external_role_allows_matching_partner():
    dep = require_external_role("PARTNER")
    u = _fake_user("PARTNER")
    assert dep(u) is u  # 통과


def test_require_external_role_rejects_other_external():
    dep = require_external_role("PARTNER")
    with pytest.raises(HTTPException) as exc:
        dep(_fake_user("INVESTOR"))  # 외부역할이지만 allowed 아님
    assert exc.value.status_code == 403


def test_require_external_role_rejects_internal_staff():
    dep = require_external_role("PARTNER")
    with pytest.raises(HTTPException) as exc:
        dep(_fake_user("STAFF"))  # 내부역할은 EXTERNAL_ROLES 아님 → 거부
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# 4. 격리 상수 무결성 — 외부역할이 내부 인가 상수에 절대 섞이지 않음
# ---------------------------------------------------------------------------
def test_external_roles_isolated_from_internal_constants():
    from auth import PERMISSION_MATRIX, ROLE_LEVEL

    assert EXTERNAL_ROLES == {"PARTNER", "INVESTOR"}
    for role in EXTERNAL_ROLES:
        assert role not in ROLE_LEVEL  # require_role → level 0 → 거부
        for allowed in PERMISSION_MATRIX.values():
            assert role not in allowed  # require_permission → 미포함 → 거부


def test_require_role_and_permission_reject_external_role():
    # require_role("STAFF"): 외부역할 level 0 < 1 → 403
    with pytest.raises(HTTPException) as e1:
        require_role("STAFF")(_fake_user("PARTNER"))
    assert e1.value.status_code == 403
    # require_permission("master.write"): 매트릭스 미포함 → 403
    with pytest.raises(HTTPException) as e2:
        require_permission("master.write")(_fake_user("INVESTOR"))
    assert e2.value.status_code == 403


# ---------------------------------------------------------------------------
# 5. 사각지대 봉합 — get_current_user가 외부역할을 원천 거부하므로, get_current_user만
#    건 내부 조회 엔드포인트도 외부역할이면 403(전면 격리).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/api/v1/projects", "/api/v1/clients", "/api/v1/buyers"])
def test_external_blocked_on_bare_read(client, partner_headers, path):
    r = client.get(path, headers=partner_headers)
    assert r.status_code == 403, r.text
