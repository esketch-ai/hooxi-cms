"""OBSERVER(내부 읽기전용 역할) 격리 불변식 — OB-1.

핵심 불변식: OBSERVER는 auth.py의 ROLE_LEVEL·PERMISSION_MATRIX에 절대 등록하지 않는다.
- get_current_user(:140)는 EXTERNAL_ROLES(PARTNER/INVESTOR)만 원천 거부하므로,
  내부역할인 OBSERVER는 get_current_user만 건 관찰 조회 엔드포인트를 통과한다(200).
- require_role/require_permission은 미등록 역할을 level 0/거부 처리하므로, OBSERVER는
  모든 쓰기·관리 GET에서 코드 변경 없이 전수 403이 된다(= 쓰기 자동 격리).
  이 자동 격리가 OBSERVER 도입의 근거이며, 아래 회귀락(4)이 향후 실수로 인한
  ROLE_LEVEL/PERMISSION_MATRIX 편입을 실패로 잡는다.

역할 부여는 schemas.py 정규식(UserApproveRequest/UserRoleRequest/UserCreateRequest)에
OBSERVER를 추가해 허용한다 — auth.py는 무변경.
"""

import pytest

import models


# ---------------------------------------------------------------------------
# OBSERVER ACTIVE 계정 직접 생성 + dev-login 토큰 발급 헬퍼
# (test_external_isolation의 _ensure_external_user와 동일 방식 — role만 OBSERVER)
# ---------------------------------------------------------------------------
def _ensure_user(user_id, email, role, status="ACTIVE", **extra):
    db = models.SessionLocal()
    try:
        u = db.get(models.User, user_id)
        if u is None:
            u = models.User(user_id=user_id, email=email, name=email.split("@")[0])
            db.add(u)
        u.role = role
        u.status = status
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
def observer_headers(client):
    _ensure_user("u-observer", "observer@hooxipartners.com", "OBSERVER")
    return _login(client, "observer@hooxipartners.com")


# ---------------------------------------------------------------------------
# 1. 역할 부여 — ADMIN이 OBSERVER를 부여할 수 있다(정규식 통과)
# ---------------------------------------------------------------------------
def test_admin_can_assign_observer_via_role(client, admin_headers):
    """PUT /users/{id}/role role=OBSERVER → 200 (UserRoleRequest 정규식 통과)."""
    _ensure_user("u-obs-target", "obs-target@hooxipartners.com", "STAFF")
    r = client.put(
        "/api/v1/users/u-obs-target/role",
        headers=admin_headers,
        json={"role": "OBSERVER"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "OBSERVER"


def test_admin_can_create_observer(client, admin_headers):
    """POST /users role=OBSERVER → 201 (UserCreateRequest 정규식 통과)."""
    r = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={"email": "obs-new@hooxipartners.com", "name": "관찰", "role": "OBSERVER"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "OBSERVER"


# ---------------------------------------------------------------------------
# 2. 쓰기 전량 403 — require_permission/require_role이 OBSERVER를 원천 거부
#    (의존성이 body/경로 검증보다 먼저 거부 → 더미 body·id로도 403)
# ---------------------------------------------------------------------------
def test_observer_blocked_post_clients(client, observer_headers):
    r = client.post("/api/v1/clients", headers=observer_headers, json={})
    assert r.status_code == 403, r.text


def test_observer_blocked_put_project(client, observer_headers):
    r = client.put("/api/v1/projects/any-id", headers=observer_headers, json={})
    assert r.status_code == 403, r.text


def test_observer_blocked_post_project_sale(client, observer_headers):
    r = client.post("/api/v1/projects/any-id/sales", headers=observer_headers, json={})
    assert r.status_code == 403, r.text


def test_observer_blocked_post_users(client, observer_headers):
    r = client.post("/api/v1/users", headers=observer_headers, json={})
    assert r.status_code == 403, r.text


def test_observer_blocked_delete_project(client, observer_headers):
    # 정산/삭제류 elevated 쓰기(client.delete: MANAGER+) — OBSERVER 거부
    r = client.delete("/api/v1/projects/any-id", headers=observer_headers)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 3. 관찰 조회 200 — get_current_user만 건 내부 조회는 OBSERVER 통과
# ---------------------------------------------------------------------------
_OBSERVABLE_GET = [
    "/api/v1/dashboard/stats",
    "/api/v1/projects",
    "/api/v1/projects/stage-delays",
    "/api/v1/finance-ledger",
    "/api/v1/asset-vehicles",
    "/api/v1/clients",
]


@pytest.mark.parametrize("path", _OBSERVABLE_GET)
def test_observer_can_read(client, observer_headers, path):
    r = client.get(path, headers=observer_headers)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# 3-1. 관리 GET 배제 — require_role("MANAGER") 엔드포인트는 OBSERVER 403
# ---------------------------------------------------------------------------
def test_observer_blocked_on_users_list(client, observer_headers):
    r = client.get("/api/v1/users", headers=observer_headers)
    assert r.status_code == 403, r.text


# ---------------------------------------------------------------------------
# 4. 격리 불변식 회귀락 — OBSERVER가 내부 인가 상수에 절대 섞이지 않음.
#    향후 실수로 ROLE_LEVEL/PERMISSION_MATRIX에 추가되면(=쓰기 격리 붕괴) 실패한다.
# ---------------------------------------------------------------------------
def test_observer_isolated_from_write_constants():
    from auth import EXTERNAL_ROLES, PERMISSION_MATRIX, ROLE_LEVEL

    assert "OBSERVER" not in ROLE_LEVEL  # require_role → level 0 → 쓰기·관리GET 거부
    for allowed in PERMISSION_MATRIX.values():
        assert "OBSERVER" not in allowed  # require_permission → 미포함 → 거부
    assert "OBSERVER" not in EXTERNAL_ROLES  # 내부역할 — 포털/외부격리 상수와도 분리
