"""이메일+PIN 로그인 (POST /auth/email-login) — 도메인 제한·JIT PENDING·PIN 게이트."""

LOGIN = "/api/v1/auth/email-login"


def test_wrong_domain_rejected(client):
    resp = client.post(LOGIN, json={"email": "outsider@gmail.com"})
    assert resp.status_code == 403


def test_unknown_email_becomes_pending(client):
    resp = client.post(LOGIN, json={"email": "newbie@hooxipartners.com"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "PENDING"
    # 재시도해도 여전히 PENDING (중복 생성 없음)
    resp2 = client.post(LOGIN, json={"email": "newbie@hooxipartners.com"})
    assert resp2.json()["status"] == "PENDING"


def test_pending_user_stays_pending(client):
    resp = client.post(LOGIN, json={"email": "pending@hooxipartners.com"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "PENDING"


def test_active_without_pin_gets_tokens(client):
    """최초 로그인(PIN 미설정): 즉시 토큰 발급 → 프론트가 PIN 설정 강제."""
    resp = client.post(LOGIN, json={"email": "staff@hooxipartners.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "OK"
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["pin_set"] is False


def test_pin_gate_after_pin_set(client):
    """PIN 설정 후에는 PIN 없인 PIN_REQUIRED, 오답 401, 정답 OK."""
    first = client.post(LOGIN, json={"email": "manager@hooxipartners.com"}).json()
    headers = {"Authorization": "Bearer {0}".format(first["access_token"])}
    assert (
        client.post("/api/v1/auth/pin", json={"pin": "4321"}, headers=headers).status_code
        == 200
    )

    no_pin = client.post(LOGIN, json={"email": "manager@hooxipartners.com"})
    assert no_pin.json()["status"] == "PIN_REQUIRED"

    wrong = client.post(LOGIN, json={"email": "manager@hooxipartners.com", "pin": "0000"})
    assert wrong.status_code == 401

    ok = client.post(LOGIN, json={"email": "manager@hooxipartners.com", "pin": "4321"})
    assert ok.status_code == 200
    assert ok.json()["status"] == "OK"
    assert ok.json()["user"]["pin_set"] is True
