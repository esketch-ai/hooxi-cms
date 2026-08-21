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


def test_pass_duration_and_expiry(client, manager_headers, staff_headers):
    """이용권(1일/1주/1개월/연간) — 만료일 설정·만료 후 포털 401·재발급으로 연장."""
    from datetime import timedelta

    import models as m
    db = m.SessionLocal()
    try:
        _cleanup(db)
    finally:
        db.close()
    ca = _mk_client(client, staff_headers, "TESTINV이용권운수")
    # 1일권 발급
    r = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "pass@inv-test.example", "role": "PARTNER", "client_id": ca,
        "duration": "1d",
    })
    assert r.status_code == 201, r.text
    uid = r.json()["user_id"]
    assert r.json()["portal_expires_at"] is not None
    # 매직링크 verify → 포털 접근 정상
    from auth import create_magic_token
    db = m.SessionLocal()
    try:
        u = db.get(m.User, uid)
        tok = create_magic_token(u)
    finally:
        db.close()
    rv = client.post("/api/v1/portal/auth/verify", json={"token": tok})
    assert rv.status_code == 200, rv.text
    access = rv.json()["access_token"]
    assert client.get("/api/v1/portal/me",
                      headers={"Authorization": "Bearer " + access}).status_code == 200
    # 만료 처리(과거로 밀기) → 기존 세션도 즉시 401, verify도 401
    db = m.SessionLocal()
    try:
        u = db.get(m.User, uid)
        u.portal_expires_at = m.utcnow() - timedelta(hours=1)
        db.commit()
    finally:
        db.close()
    r401 = client.get("/api/v1/portal/me", headers={"Authorization": "Bearer " + access})
    assert r401.status_code == 401
    assert "만료" in r401.json()["detail"]
    assert client.post("/api/v1/portal/auth/verify", json={"token": tok}).status_code == 401
    # 재발급(연간권) → 만료 연장, 다시 접근 가능
    rr = client.post(f"{EXTERNAL}/{uid}/resend-link", headers=manager_headers,
                     json={"duration": "365d"})
    assert rr.status_code == 200, rr.text
    db = m.SessionLocal()
    try:
        u = db.get(m.User, uid)
        assert u.portal_expires_at > m.utcnow() + timedelta(days=300)
        tok2 = create_magic_token(u)
    finally:
        db.close()
    assert client.post("/api/v1/portal/auth/verify", json={"token": tok2}).status_code == 200
    # 잘못된 기간 → 422
    bad = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "pass2@inv-test.example", "role": "PARTNER", "client_id": ca,
        "duration": "3d",
    })
    assert bad.status_code == 422
    db = m.SessionLocal()
    try:
        _cleanup(db)
    finally:
        db.close()


def test_login_config_public_endpoint(client, admin_headers):
    """무인증 로그인 설정 — kakao_channel_url 화이트리스트만, https 외 값 은닉."""
    import models as m
    # 무인증 호출 가능
    r = client.get("/api/v1/auth/login-config")
    assert r.status_code == 200
    db = m.SessionLocal()
    try:
        row = db.get(m.Config, "kakao_channel_url")
        if row is None:
            row = m.Config(config_key="kakao_channel_url")
            db.add(row)
        row.config_value = '"https://pf.kakao.com/_testch"'
        db.commit()
    finally:
        db.close()
    r2 = client.get("/api/v1/auth/login-config")
    assert r2.json()["kakao_channel_url"] == "https://pf.kakao.com/_testch"
    # https 아닌 값은 노출 금지
    db = m.SessionLocal()
    try:
        db.get(m.Config, "kakao_channel_url").config_value = '"javascript:alert(1)"'
        db.commit()
    finally:
        db.close()
    assert client.get("/api/v1/auth/login-config").json()["kakao_channel_url"] is None
    db = m.SessionLocal()
    try:
        db.get(m.Config, "kakao_channel_url").config_value = '""'
        db.commit()
    finally:
        db.close()
