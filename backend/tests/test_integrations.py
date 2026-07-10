"""연동 설정 관리 테스트 — /api/v1/integrations (ADMIN 전용).

- RBAC: STAFF/MANAGER 403
- GET 목록: 시크릿 값 미노출 · source 판별(env vs db)
- PUT 저장: DB에 "enc:" 접두 암호문만(평문 미저장) · null 삭제 · 미전달 유지
- resolve(): DB 우선 → env 폴백 → 기본값
- 감사 로그 INTEGRATION_CHANGE: 변경 키 목록만(값 없음) · history "***" 마스킹
- Dropbox OAuth exchange(httpx 모킹): 성공 저장 / 실패 502
- test 엔드포인트(모킹): solapi·gmail·dropbox·kakao_bot
- 기존 서비스 회귀: kakao_service.webhook_secret()이 DB 값을 읽는지

주의: crypto는 키를 호출 시점에 읽으므로 ASSET_ENC_KEY를 모듈 상단에서 주입한다
(tests/test_p2_smoke.py 패턴).
"""

import base64
import json
import os

os.environ["ASSET_ENC_KEY"] = base64.b64encode(b"integrations-test-32byte-key-012").decode()

import pytest  # noqa: E402

import models  # noqa: E402
from models import AuditLog, Config, ConfigHistory  # noqa: E402
from services import dropbox_storage, integration_config, kakao_service  # noqa: E402

API = "/api/v1"

SECRET_PLAINTEXT = "super-secret-app-password-01!"
WEBHOOK_SECRET_DB = "db-webhook-secret-xyz"


def _db():
    return models.SessionLocal()


@pytest.fixture(scope="module", autouse=True)
def _cleanup_integrations(client):
    """모듈 종료 시 integration.* 행·이력 제거 + 캐시 무효화 — 타 모듈 env 폴백 보전."""
    integration_config.bump_version()
    yield
    db = _db()
    try:
        db.query(ConfigHistory).filter(
            ConfigHistory.config_key.like("integration.%")
        ).delete(synchronize_session=False)
        db.query(Config).filter(Config.config_key.like("integration.%")).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()
    integration_config.bump_version()


@pytest.fixture(scope="module")
def manager_headers(client):
    resp = client.post(API + "/auth/dev-login", json={"email": "manager@hooxipartners.com"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": "Bearer {0}".format(resp.json()["access_token"])}


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


# ---------------------------------------------------------------------------
# RBAC — 전부 ADMIN 전용
# ---------------------------------------------------------------------------
def test_rbac_staff_manager_403(client, staff_headers, manager_headers):
    for headers in (staff_headers, manager_headers):
        assert client.get(API + "/integrations", headers=headers).status_code == 403
        assert (
            client.put(
                API + "/integrations/gmail",
                headers=headers,
                json={"values": {"GMAIL_SENDER": "x@hooxipartners.com"}},
            ).status_code
            == 403
        )
        assert (
            client.post(API + "/integrations/gmail/test", headers=headers).status_code == 403
        )
    assert client.get(API + "/integrations").status_code == 401  # 미인증


# ---------------------------------------------------------------------------
# GET 목록 — REGISTRY 구조 · source 판별 · 시크릿 값 미노출
# ---------------------------------------------------------------------------
def test_list_integrations_env_source(client, admin_headers, monkeypatch):
    monkeypatch.setenv("GMAIL_SENDER", "env-sender@hooxipartners.com")
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)

    resp = client.get(API + "/integrations", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    items = {item["name"]: item for item in resp.json()["items"]}
    assert set(items) == {"dropbox", "solapi", "kakao_bot", "gmail", "naver_works"}

    gmail = {f["key"]: f for f in items["gmail"]["fields"]}
    assert gmail["GMAIL_SENDER"]["configured"] is True
    assert gmail["GMAIL_SENDER"]["source"] == "env"
    assert gmail["GMAIL_APP_PASSWORD"]["configured"] is False
    assert gmail["GMAIL_APP_PASSWORD"]["source"] is None
    assert gmail["GMAIL_APP_PASSWORD"]["secret"] is True

    # kakao_bot에는 마스킹된 웹훅 URL 노출
    assert "secret=***" in items["kakao_bot"]["webhook_url"]
    # 어떤 응답에도 env 값 원문(시크릿 아님)은 노출돼도 되지만, 값 필드 자체가 없어야 함
    assert "value" not in gmail["GMAIL_SENDER"]


# ---------------------------------------------------------------------------
# PUT 저장 — 암호화 저장 · 평문 미저장 · source=db
# ---------------------------------------------------------------------------
def test_put_saves_encrypted_secret(client, admin_headers):
    resp = client.put(
        API + "/integrations/gmail",
        headers=admin_headers,
        json={
            "values": {
                "GMAIL_SENDER": "db-sender@hooxipartners.com",
                "GMAIL_APP_PASSWORD": SECRET_PLAINTEXT,
            }
        },
    )
    assert resp.status_code == 200, resp.text
    assert SECRET_PLAINTEXT not in resp.text  # 응답에 시크릿 원문 미노출
    fields = {f["key"]: f for f in resp.json()["fields"]}
    assert fields["GMAIL_SENDER"]["source"] == "db"
    assert fields["GMAIL_APP_PASSWORD"]["source"] == "db"

    db = _db()
    try:
        row = db.get(Config, "integration.gmail")
        assert row is not None
        stored = json.loads(row.config_value)
        assert stored["GMAIL_SENDER"] == "db-sender@hooxipartners.com"  # 일반 필드는 평문
        assert stored["GMAIL_APP_PASSWORD"].startswith("enc:")  # 시크릿은 암호문
        assert SECRET_PLAINTEXT not in row.config_value  # 평문 미저장
    finally:
        db.close()


def test_resolve_prefers_db_over_env(monkeypatch):
    monkeypatch.setenv("GMAIL_SENDER", "env-sender@hooxipartners.com")
    assert integration_config.resolve("GMAIL_SENDER") == "db-sender@hooxipartners.com"
    # 시크릿도 DB 복호화 값 반환
    assert integration_config.resolve("GMAIL_APP_PASSWORD") == SECRET_PLAINTEXT


def test_resolve_env_fallback_and_default(monkeypatch):
    # DB 미저장 키 → env 폴백 (env는 캐시 없이 호출 시점에 읽음)
    monkeypatch.setenv("SOLAPI_SENDER", "0212345678")
    assert integration_config.resolve("SOLAPI_SENDER") == "0212345678"
    monkeypatch.delenv("SOLAPI_SENDER", raising=False)
    assert integration_config.resolve("SOLAPI_SENDER") is None
    # DB·env 모두 없으면 REGISTRY 기본값
    monkeypatch.delenv("DROPBOX_ROOT", raising=False)
    assert integration_config.resolve("DROPBOX_ROOT") == "/Hooxi-CMS"
    monkeypatch.delenv("KAKAO_EVENT_NAME", raising=False)
    assert integration_config.resolve("KAKAO_EVENT_NAME") == "staff_reply"


def test_audit_log_records_keys_only(client, admin_headers):
    db = _db()
    try:
        logs = (
            db.query(AuditLog)
            .filter(AuditLog.action == "INTEGRATION_CHANGE", AuditLog.target_id == "gmail")
            .all()
        )
        assert logs, "INTEGRATION_CHANGE 감사 로그가 없음"
        latest = logs[-1]
        assert latest.target_type == "INTEGRATION"
        # 변경 키 목록만 — redact 안전망 우회로 키 이름은 온전히 남는다
        assert "GMAIL_SENDER" in latest.new_value
        assert "GMAIL_APP_PASSWORD" in latest.new_value
        # 값(평문·암호문)은 절대 기록 금지
        for log in logs:
            assert SECRET_PLAINTEXT not in (log.new_value or "")
            assert SECRET_PLAINTEXT not in (log.old_value or "")
            assert "enc:" not in (log.new_value or "")
    finally:
        db.close()


def test_history_masks_secrets(client, admin_headers):
    db = _db()
    try:
        rows = (
            db.query(ConfigHistory)
            .filter(ConfigHistory.config_key == "integration.gmail")
            .all()
        )
        assert rows
        for row in rows:
            for value in (row.old_value, row.new_value):
                if not value:
                    continue
                assert SECRET_PLAINTEXT not in value
                assert "enc:" not in value  # 암호문도 이력에 남기지 않음
        parsed = json.loads(rows[-1].new_value)
        assert parsed["GMAIL_APP_PASSWORD"] == "***"
        assert parsed["GMAIL_SENDER"] == "db-sender@hooxipartners.com"
    finally:
        db.close()


def test_put_null_deletes_key(client, admin_headers, monkeypatch):
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    resp = client.put(
        API + "/integrations/gmail",
        headers=admin_headers,
        json={"values": {"GMAIL_APP_PASSWORD": None}},
    )
    assert resp.status_code == 200, resp.text
    fields = {f["key"]: f for f in resp.json()["fields"]}
    assert fields["GMAIL_APP_PASSWORD"]["configured"] is False
    assert fields["GMAIL_APP_PASSWORD"]["source"] is None
    # 미전달 키(GMAIL_SENDER)는 유지
    assert fields["GMAIL_SENDER"]["source"] == "db"

    db = _db()
    try:
        stored = json.loads(db.get(Config, "integration.gmail").config_value)
        assert "GMAIL_APP_PASSWORD" not in stored
        assert stored["GMAIL_SENDER"] == "db-sender@hooxipartners.com"
    finally:
        db.close()
    assert integration_config.resolve("GMAIL_APP_PASSWORD") is None


def test_put_validation_errors(client, admin_headers):
    assert (
        client.put(
            API + "/integrations/unknown", headers=admin_headers, json={"values": {"A": "b"}}
        ).status_code
        == 404
    )
    assert (
        client.put(
            API + "/integrations/gmail",
            headers=admin_headers,
            json={"values": {"NOT_A_KEY": "x"}},
        ).status_code
        == 422
    )
    assert (
        client.put(
            API + "/integrations/gmail", headers=admin_headers, json={"values": {}}
        ).status_code
        == 422
    )


def test_put_secret_without_enc_key_503(client, admin_headers, monkeypatch):
    monkeypatch.delenv("ASSET_ENC_KEY", raising=False)
    resp = client.put(
        API + "/integrations/gmail",
        headers=admin_headers,
        json={"values": {"GMAIL_APP_PASSWORD": "new-secret"}},
    )
    assert resp.status_code == 503
    assert "ASSET_ENC_KEY" in resp.json()["detail"]
    # 일반 필드만이면 키 없이도 저장 가능
    resp = client.put(
        API + "/integrations/gmail",
        headers=admin_headers,
        json={"values": {"GMAIL_SENDER": "db-sender@hooxipartners.com"}},
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 기존 서비스 회귀 — DB 저장값이 실제 서비스 경로에 반영되는지
# ---------------------------------------------------------------------------
def test_kakao_webhook_secret_reads_db_value(client, admin_headers, monkeypatch):
    monkeypatch.delenv("KAKAO_WEBHOOK_SECRET", raising=False)
    resp = client.put(
        API + "/integrations/kakao_bot",
        headers=admin_headers,
        json={"values": {"KAKAO_WEBHOOK_SECRET": WEBHOOK_SECRET_DB}},
    )
    assert resp.status_code == 200, resp.text

    # 서비스 계층: DB 값 복호화 반환
    assert kakao_service.webhook_secret() == WEBHOOK_SECRET_DB

    # 실제 웹훅 엔드포인트도 DB 시크릿으로 통과 (env 미설정 상태)
    payload = {
        "userRequest": {
            "user": {"id": "integ-test-user", "properties": {}},
            "utterance": "안녕하세요",
        },
        "action": {"clientExtra": {}},
    }
    ok = client.post(
        API + "/kakao/webhook", params={"secret": WEBHOOK_SECRET_DB}, json=payload
    )
    assert ok.status_code == 200, ok.text
    bad = client.post(API + "/kakao/webhook", params={"secret": "wrong"}, json=payload)
    assert bad.status_code == 403


def test_webhook_url_full_reveals_with_audit(client, admin_headers):
    resp = client.get(API + "/integrations/kakao_bot/webhook-url", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert WEBHOOK_SECRET_DB in resp.json()["url"]

    db = _db()
    try:
        reveal = (
            db.query(AuditLog)
            .filter(AuditLog.action == "INTEGRATION_REVEAL", AuditLog.target_id == "kakao_bot")
            .all()
        )
        assert reveal and reveal[-1].new_value == "webhook_url"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 연결 테스트 엔드포인트 (모킹)
# ---------------------------------------------------------------------------
def test_solapi_test_endpoint_mocked(client, admin_headers, monkeypatch):
    from routers import integrations as integ_router

    monkeypatch.setenv("SOLAPI_API_KEY", "k")
    monkeypatch.setenv("SOLAPI_API_SECRET", "s")

    monkeypatch.setattr(
        integ_router.httpx, "get", lambda url, **kw: _FakeResponse(200, {"balance": 5000})
    )
    resp = client.post(API + "/integrations/solapi/test", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    monkeypatch.setattr(integ_router.httpx, "get", lambda url, **kw: _FakeResponse(401))
    resp = client.post(API + "/integrations/solapi/test", headers=admin_headers)
    assert resp.json()["ok"] is False
    assert "401" in resp.json()["message"]


def test_gmail_test_endpoint_mocked(client, admin_headers, monkeypatch):
    from routers import integrations as integ_router

    # 발신자는 DB 저장값, 비밀번호는 env 폴백 — 혼합 해석 확인
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "env-app-pass")
    captured = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            captured["host"] = host

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self, user, password):
            captured["login"] = (user, password)

    monkeypatch.setattr(integ_router.smtplib, "SMTP_SSL", FakeSMTP)
    resp = client.post(API + "/integrations/gmail/test", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert captured["login"] == ("db-sender@hooxipartners.com", "env-app-pass")


def test_kakao_bot_test_checks_required_fields(client, admin_headers, monkeypatch):
    monkeypatch.delenv("KAKAO_BOT_ID", raising=False)
    monkeypatch.delenv("KAKAO_EVENT_API_KEY", raising=False)
    resp = client.post(API + "/integrations/kakao_bot/test", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is False  # BOT_ID·EVENT_API_KEY 미설정
    assert "KAKAO_BOT_ID" in resp.json()["message"]

    monkeypatch.setenv("KAKAO_BOT_ID", "bot-1")
    monkeypatch.setenv("KAKAO_EVENT_API_KEY", "ek")
    resp = client.post(API + "/integrations/kakao_bot/test", headers=admin_headers)
    assert resp.json()["ok"] is True  # WEBHOOK_SECRET은 DB(source=db)


# ---------------------------------------------------------------------------
# Dropbox OAuth 마법사
# ---------------------------------------------------------------------------
def test_dropbox_authorize_url_requires_app_key(client, admin_headers, monkeypatch):
    monkeypatch.delenv("DROPBOX_APP_KEY", raising=False)
    resp = client.post(API + "/integrations/dropbox/oauth/authorize-url", headers=admin_headers)
    assert resp.status_code == 422

    resp = client.put(
        API + "/integrations/dropbox",
        headers=admin_headers,
        json={"values": {"DROPBOX_APP_KEY": "app-key-1", "DROPBOX_APP_SECRET": "app-sec-1"}},
    )
    assert resp.status_code == 200, resp.text

    resp = client.post(API + "/integrations/dropbox/oauth/authorize-url", headers=admin_headers)
    assert resp.status_code == 200
    url = resp.json()["url"]
    assert "client_id=app-key-1" in url
    assert "token_access_type=offline" in url


def test_dropbox_oauth_exchange_failure_502(client, admin_headers, monkeypatch):
    from routers import integrations as integ_router

    monkeypatch.setattr(
        integ_router.httpx,
        "post",
        lambda url, **kw: _FakeResponse(400, {"error": "invalid_grant"}),
    )
    resp = client.post(
        API + "/integrations/dropbox/oauth/exchange",
        headers=admin_headers,
        json={"code": "bad-code"},
    )
    assert resp.status_code == 502
    assert "토큰 교환" in resp.json()["detail"]


def test_dropbox_oauth_exchange_success_saves_token(client, admin_headers, monkeypatch):
    from routers import integrations as integ_router

    exchanged = {}

    def fake_post(url, **kwargs):
        exchanged["url"] = url
        exchanged["data"] = kwargs.get("data")
        exchanged["auth"] = kwargs.get("auth")
        return _FakeResponse(200, {"refresh_token": "rt-plain-123", "token_type": "bearer"})

    class FakeAccount:
        email = "ops@hooxipartners.com"
        team = None

    class FakeDbx:
        def users_get_current_account(self):
            return FakeAccount()

    monkeypatch.setattr(integ_router.httpx, "post", fake_post)
    monkeypatch.setattr(dropbox_storage, "_get_client", lambda: FakeDbx())

    resp = client.post(
        API + "/integrations/dropbox/oauth/exchange",
        headers=admin_headers,
        json={"code": "good-code"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert "ops@hooxipartners.com" in body["message"]
    assert exchanged["data"]["grant_type"] == "authorization_code"
    assert exchanged["auth"] == ("app-key-1", "app-sec-1")  # DB 저장 앱 키·시크릿 사용

    db = _db()
    try:
        stored = json.loads(db.get(Config, "integration.dropbox").config_value)
        assert stored["DROPBOX_REFRESH_TOKEN"].startswith("enc:")
        assert "rt-plain-123" not in json.dumps(stored)
    finally:
        db.close()
    assert integration_config.resolve("DROPBOX_REFRESH_TOKEN") == "rt-plain-123"


def test_dropbox_test_endpoint_mocked(client, admin_headers, monkeypatch):
    class FakeAccount:
        email = "ops@hooxipartners.com"
        team = object()  # 팀 계정

    class FakeDbx:
        def users_get_current_account(self):
            return FakeAccount()

    monkeypatch.setattr(dropbox_storage, "_get_client", lambda: FakeDbx())
    resp = client.post(API + "/integrations/dropbox/test", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "팀 계정" in body["message"]
