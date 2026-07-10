"""계정 관리 확장 — 직접 생성·이름/직급 수정·재활성화 (+ 감사 기록)."""

import models


def _audits(action):
    db = models.SessionLocal()
    try:
        return (
            db.query(models.AuditLog)
            .filter(models.AuditLog.action == action)
            .order_by(models.AuditLog.created_at.desc())
            .all()
        )
    finally:
        db.close()


def test_create_user_direct(client, admin_headers, staff_headers):
    # RBAC — ADMIN 전용
    resp = client.post(
        "/api/v1/users",
        json={"email": "direct@hooxipartners.com"},
        headers=staff_headers,
    )
    assert resp.status_code == 403

    # 도메인 외 422
    resp = client.post(
        "/api/v1/users", json={"email": "x@gmail.com"}, headers=admin_headers
    )
    assert resp.status_code == 422

    # 정상 생성 — 즉시 ACTIVE, 감사 기록
    resp = client.post(
        "/api/v1/users",
        json={
            "email": "direct@hooxipartners.com",
            "name": "직접생성",
            "position": "대리",
            "role": "MANAGER",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "ACTIVE" and body["role"] == "MANAGER"
    assert body["name"] == "직접생성" and body["position"] == "대리"
    logs = _audits("USER_CREATE")
    assert logs and logs[0].target_id == body["user_id"]

    # 즉시 이메일 로그인 가능(PIN 미설정 → 토큰 발급)
    login = client.post(
        "/api/v1/auth/email-login", json={"email": "direct@hooxipartners.com"}
    )
    assert login.json()["status"] == "OK"

    # 중복 409
    resp = client.post(
        "/api/v1/users",
        json={"email": "direct@hooxipartners.com"},
        headers=admin_headers,
    )
    assert resp.status_code == 409


def test_update_user_name_position(client, admin_headers):
    created = client.post(
        "/api/v1/users",
        json={"email": "edit-me@hooxipartners.com", "name": "수정전"},
        headers=admin_headers,
    ).json()
    uid = created["user_id"]

    resp = client.put(
        "/api/v1/users/{0}".format(uid),
        json={"name": "수정후", "position": "과장"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "수정후" and resp.json()["position"] == "과장"
    logs = _audits("USER_UPDATE")
    assert logs and "수정전" in (logs[0].new_value or "") and "수정후" in logs[0].new_value


def test_reactivate_user(client, admin_headers):
    created = client.post(
        "/api/v1/users",
        json={"email": "revive@hooxipartners.com"},
        headers=admin_headers,
    ).json()
    uid = created["user_id"]

    # ACTIVE 상태에서 재활성화 시도 → 409
    resp = client.put("/api/v1/users/{0}/reactivate".format(uid), headers=admin_headers)
    assert resp.status_code == 409

    client.put("/api/v1/users/{0}/deactivate".format(uid), headers=admin_headers)
    resp = client.put("/api/v1/users/{0}/reactivate".format(uid), headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ACTIVE"
    logs = _audits("USER_REACTIVATE")
    assert logs and logs[0].target_id == uid

    # 재활성화 후 로그인 가능
    login = client.post(
        "/api/v1/auth/email-login", json={"email": "revive@hooxipartners.com"}
    )
    assert login.json()["status"] == "OK"
