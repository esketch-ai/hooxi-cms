"""OBSERVER(경영전략실) 격리 불변식 — OB-1 (정책 A: 엄격 화이트리스트).

핵심 불변식: OBSERVER는 auth.py의 ROLE_LEVEL·PERMISSION_MATRIX에 절대 등록하지 않는다.
- get_current_user는 OBSERVER에 대해 관찰 스코프 화이트리스트(OBSERVER_SCOPE_*)의 API만
  통과시킨다(200). 화이트리스트 밖의 내부 조회·export는 이 지점에서 403이 된다 —
  넓은 조회 허용이 아니라 '관찰 스코프만 허용'.
- require_role/require_permission은 미등록 역할을 level 0/거부 처리하므로, OBSERVER는
  모든 쓰기·관리 GET에서 코드 변경 없이 전수 403이 된다(= 쓰기 자동 격리).
  이 자동 격리가 OBSERVER 도입의 근거이며, 아래 회귀락(4)이 향후 실수로 인한
  ROLE_LEVEL/PERMISSION_MATRIX 편입을 실패로 잡는다.

역할 부여는 schemas.py 정규식(UserApproveRequest/UserRoleRequest/UserCreateRequest)에
OBSERVER를 추가해 허용한다.
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
# 3. 관찰 조회 200 — 관찰 스코프 화이트리스트(OBSERVER_SCOPE_*) API만 OBSERVER 통과
#    (/observe 화면이 분해되는 4개 API + me/codes/badge 기반 API)
# ---------------------------------------------------------------------------
_OBSERVABLE_GET = [
    "/api/v1/users/me",
    "/api/v1/codes?category=CLIENT_TYPE",  # codes는 category 필수 — 쿼리는 path 밖이라 화이트리스트 매칭 무관
    "/api/v1/dashboard/stats",
    "/api/v1/projects/stage-delays",
    "/api/v1/finance-ledger",
    "/api/v1/asset-vehicles",
    "/api/v1/chat/badge",
]


@pytest.mark.parametrize("path", _OBSERVABLE_GET)
def test_observer_can_read(client, observer_headers, path):
    r = client.get(path, headers=observer_headers)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# 3-1. 비(非)스코프 내부 GET 403 — 화이트리스트 밖 조회는 get_current_user에서 차단.
#    (경로가 실제 라우터 root와 일치 → 404가 아닌 403임을 보장)
#    export(/finance-ledger/export·/asset-vehicles/export)는 정확매칭 제외 + MANAGER 게이트.
# ---------------------------------------------------------------------------
_NON_SCOPE_GET = [
    "/api/v1/clients",
    "/api/v1/buyers",
    "/api/v1/projects",
    "/api/v1/projects/any-id",
    "/api/v1/histories",
    "/api/v1/reports",
    "/api/v1/documents",
    "/api/v1/schedules",
    "/api/v1/audit-logs",
    "/api/v1/external-accounts",
    "/api/v1/users",
    "/api/v1/finance-ledger/export",
    "/api/v1/asset-vehicles/export",
]


@pytest.mark.parametrize("path", _NON_SCOPE_GET)
def test_observer_blocked_on_non_scope_get(client, observer_headers, path):
    r = client.get(path, headers=observer_headers)
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
