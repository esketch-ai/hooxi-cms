"""포털 발급 정책 확장 — 내부 이메일 공존·로그인 스코프·영업활동 이력 자동 적재."""

import models

EXTERNAL = "/api/v1/external-accounts"


def _cleanup(db):
    db.query(models.ActivityHistory).filter(
        models.ActivityHistory.activity_type == "PORTAL",
        models.ActivityHistory.title.like("%TESTINV%")).delete(synchronize_session=False)
    db.query(models.User).filter(
        models.User.email.like("%@inv-test.example")).delete(synchronize_session=False)
    db.query(models.Client).filter(
        models.Client.company_name.like("TESTINV%")).delete(synchronize_session=False)
    db.commit()


def _mk_client(client, headers, name):
    r = client.post("/api/v1/clients", headers=headers,
                    json={"client_type": "TRANSPORT", "company_name": name})
    assert r.status_code == 201, r.text
    return r.json()["client_id"]


def test_internal_email_can_get_external_account(client, manager_headers, staff_headers):
    """내부 계정과 같은 이메일로도 외부 발급 가능 — 내부 로그인(dev-login)은 내부 역할 유지."""
    db = models.SessionLocal()
    try:
        _cleanup(db)
        internal = models.User(user_id="t-inv-int", email="exec@inv-test.example",
                               role="MANAGER", status="ACTIVE")
        db.add(internal)
        db.commit()
    finally:
        db.close()
    ca = _mk_client(client, staff_headers, "TESTINV운수")
    r = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "exec@inv-test.example", "role": "PARTNER", "client_id": ca,
    })
    assert r.status_code == 201, r.text
    assert r.json()["user_id"] != "t-inv-int"  # 별도 외부 계정 행
    # dev-login은 내부 역할만 매칭 — 외부 계정이 아니라 MANAGER로 로그인됨
    r2 = client.post("/api/v1/auth/dev-login", json={"email": "exec@inv-test.example"})
    assert r2.status_code == 200, r2.text
    me = client.get("/api/v1/users/me",
                    headers={"Authorization": "Bearer " + r2.json()["access_token"]})
    assert me.json()["role"] == "MANAGER"
    db = models.SessionLocal()
    try:
        _cleanup(db)
        db.query(models.User).filter_by(user_id="t-inv-int").delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_invite_logged_to_activity_history(client, manager_headers, staff_headers):
    """발급·재발급이 영업활동 이력(PORTAL, [자동])으로 적재 — 링크 원문 미기록."""
    db = models.SessionLocal()
    try:
        _cleanup(db)
    finally:
        db.close()
    ca = _mk_client(client, staff_headers, "TESTINV이력운수")
    r = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "hist@inv-test.example", "role": "PARTNER", "client_id": ca,
    })
    assert r.status_code == 201, r.text
    uid = r.json()["user_id"]
    r2 = client.post(f"{EXTERNAL}/{uid}/resend-link", headers=manager_headers)
    assert r2.status_code == 200, r2.text
    db = models.SessionLocal()
    try:
        rows = (db.query(models.ActivityHistory)
                .filter_by(client_id=ca, activity_type="PORTAL")
                .order_by(models.ActivityHistory.created_at).all())
        assert len(rows) == 2  # 발급 1 + 재발급 1
        assert rows[0].title.startswith("[자동]") and "발급" in rows[0].title
        assert "재발급" in rows[1].title
        for h in rows:
            assert "http" not in (h.content or "")  # 매직링크 원문 금지
            assert "hist@inv-test.example" in (h.content or "")
        # 고객사 상세 활동 이력 탭에서 조회됨
        rh = client.get(f"/api/v1/clients/{ca}/histories", headers=manager_headers)
        assert any(x["activity_type"] == "PORTAL" for x in rh.json())
        # ACTIVITY_TYPE 코드 시드
        code = db.query(models.Code).filter_by(category="ACTIVITY_TYPE", code="PORTAL").first()
        assert code is not None and code.label == "포털"
    finally:
        db.query(models.ActivityHistory).filter_by(client_id=ca).delete(synchronize_session=False)
        db.commit()
        _cleanup(db)
        db.close()
