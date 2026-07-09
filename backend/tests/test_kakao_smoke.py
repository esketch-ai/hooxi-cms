"""P3 카카오 채널 연동 스모크 테스트 — 웹훅 게이트·채팅 관제·알림톡·열람 토큰.

테스트는 파일 내 선언 순서대로 실행되며 세션 픽스처(임시 SQLite)를 공유한다.
오픈빌더 스킬 JSON 규격 페이로드로 웹훅을 시뮬레이션한다(외부 호출 없음).
"""

import io
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

import models
from services import email_service, kakao_service

API = "/api/v1"
WEBHOOK_SECRET = "test-hook-secret"
S = {}  # 테스트 간 공유 상태


def _login(client, email):
    resp = client.post(API + "/auth/dev-login", json={"email": email})
    assert resp.status_code == 200, resp.text
    return {"Authorization": "Bearer {0}".format(resp.json()["access_token"])}


@pytest.fixture(scope="module")
def manager_headers(client):
    return _login(client, "manager@hooxipartners.com")


@pytest.fixture(autouse=True)
def _webhook_secret(monkeypatch):
    monkeypatch.setenv("KAKAO_WEBHOOK_SECRET", WEBHOOK_SECRET)


def _skill_payload(user_key, utterance, client_extra=None):
    """오픈빌더 스킬 요청 JSON 규격."""
    return {
        "userRequest": {
            "user": {"id": user_key, "properties": {}},
            "utterance": utterance,
            "block": {"id": "fallback-block", "name": "폴백 블록"},
        },
        "bot": {"id": "demo-bot", "name": "hooxi-bot"},
        "action": {"params": {}, "clientExtra": client_extra or {}},
    }


def _webhook(client, user_key, utterance, secret=WEBHOOK_SECRET, client_extra=None):
    params = {"secret": secret} if secret is not None else {}
    return client.post(
        API + "/kakao/webhook",
        params=params,
        json=_skill_payload(user_key, utterance, client_extra),
    )


def _simple_text(body):
    return body["template"]["outputs"][0]["simpleText"]["text"]


# ---------------------------------------------------------------------------
# 웹훅 — 시크릿 검증 + 승인 게이트 (CR-3)
# ---------------------------------------------------------------------------
def test_webhook_secret_mismatch_403(client):
    resp = _webhook(client, "kakao-key-001", "안녕하세요", secret="wrong-secret")
    assert resp.status_code == 403
    resp = _webhook(client, "kakao-key-001", "안녕하세요", secret=None)
    assert resp.status_code == 403


def test_webhook_unconfigured_503(client, monkeypatch):
    monkeypatch.delenv("KAKAO_WEBHOOK_SECRET", raising=False)
    resp = _webhook(client, "kakao-key-001", "안녕하세요")
    assert resp.status_code == 503
    assert "KAKAO_WEBHOOK_SECRET" in resp.json()["detail"]


def test_webhook_unregistered_creates_pending(client, admin_headers):
    """미등록 kakao_user_key — PENDING 등록 + 오픈빌더 v2.0 규격 안내 응답."""
    resp = _webhook(client, "kakao-key-001", "보고서 관련 문의드립니다")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["version"] == "2.0"
    assert "확인" in _simple_text(body)

    # 연락처 목록 조회는 인증 필수
    assert client.get(API + "/kakao/contacts").status_code == 401

    resp = client.get(
        API + "/kakao/contacts", params={"status": "PENDING"}, headers=admin_headers
    )
    assert resp.status_code == 200
    pending = [c for c in resp.json()["items"] if c["kakao_user_key"] == "kakao-key-001"]
    assert len(pending) == 1
    S["contact_id"] = pending[0]["contact_id"]

    # 재발화 — 중복 등록 없이 PENDING 일반 안내만
    resp = _webhook(client, "kakao-key-001", "확인 부탁드립니다")
    assert resp.status_code == 200
    resp = client.get(API + "/kakao/contacts", headers=admin_headers)
    assert len([c for c in resp.json()["items"] if c["kakao_user_key"] == "kakao-key-001"]) == 1


def test_contact_approve_gate(client, admin_headers, staff_headers, manager_headers):
    """승인 게이트 — STAFF 403, MANAGER 이상 허용, 승인에는 client_id 필수."""
    # 승인 대상 고객사 생성 (구독 채널 BOTH — 보고서 KAKAO 테스트에 재사용)
    resp = client.post(
        API + "/clients",
        headers=staff_headers,
        json={
            "client_type": "TRANSPORT",
            "company_name": "카카오운수",
            "main_contact_email": "kakao@transport.example.com",
            "contract_status": "ACTIVE",
            "manager_id": "u-manager",
            "report_yn": "Y",
            "subscription": {"report_type": "월간 운행 보고서", "channel": "BOTH", "due_day": 25},
        },
    )
    assert resp.status_code == 201, resp.text
    S["client_id"] = resp.json()["client_id"]

    # STAFF는 승인 불가 (MANAGER 이상)
    resp = client.put(
        API + "/kakao/contacts/" + S["contact_id"],
        headers=staff_headers,
        json={"status": "APPROVED", "client_id": S["client_id"]},
    )
    assert resp.status_code == 403

    # 승인에는 client_id 매핑 필수
    resp = client.put(
        API + "/kakao/contacts/" + S["contact_id"],
        headers=manager_headers,
        json={"status": "APPROVED"},
    )
    assert resp.status_code == 422

    # MANAGER 승인 성공 — 고객사 매핑 + 승인자 기록
    resp = client.put(
        API + "/kakao/contacts/" + S["contact_id"],
        headers=manager_headers,
        json={
            "status": "APPROVED",
            "client_id": S["client_id"],
            "name": "김카카오",
            "phone": "010-9999-0001",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "APPROVED"
    assert body["client_id"] == S["client_id"]
    assert body["client_name"] == "카카오운수"
    assert body["approved_by_name"] == "팀장"
    assert body["approved_at"]

    resp = client.put(
        API + "/kakao/contacts/no-such-id", headers=manager_headers, json={"status": "REJECTED"}
    )
    assert resp.status_code == 404


def test_webhook_blocked_generic_reply(client, manager_headers, admin_headers):
    """차단 계정 — 일반 안내만, 메시지 미적재."""
    _webhook(client, "kakao-key-blocked", "안녕하세요")  # PENDING 등록
    resp = client.get(
        API + "/kakao/contacts", params={"status": "PENDING"}, headers=admin_headers
    )
    blocked = [c for c in resp.json()["items"] if c["kakao_user_key"] == "kakao-key-blocked"][0]
    resp = client.put(
        API + "/kakao/contacts/" + blocked["contact_id"],
        headers=manager_headers,
        json={"status": "BLOCKED"},
    )
    assert resp.status_code == 200

    resp = _webhook(client, "kakao-key-blocked", "수수료 알려주세요")
    assert resp.status_code == 200
    assert "어려운" in _simple_text(resp.json())


# ---------------------------------------------------------------------------
# 웹훅 — APPROVED 적재·스레드 재사용·민감 키워드·담당자 연결
# ---------------------------------------------------------------------------
def test_webhook_approved_creates_thread_and_message(client, staff_headers):
    resp = _webhook(client, "kakao-key-001", "7월 보고서 발송 일정 문의드립니다")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "접수" in _simple_text(body)
    # 담당자 연결 quickReply 포함
    labels = [q["label"] for q in body["template"]["quickReplies"]]
    assert "담당자 연결" in labels

    resp = client.get(
        API + "/chat/threads", params={"client_id": S["client_id"]}, headers=staff_headers
    )
    assert resp.status_code == 200
    threads = resp.json()["items"]
    assert len(threads) == 1
    thread = threads[0]
    assert thread["client_name"] == "카카오운수"
    assert thread["contact_name"] == "김카카오"
    assert thread["mode"] == "AI"
    assert thread["status"] == "OPEN"
    assert thread["last_message_preview"] == "7월 보고서 발송 일정 문의드립니다"
    S["thread_id"] = thread["thread_id"]

    msgs = client.get(
        API + "/chat/threads/{0}/messages".format(S["thread_id"]), headers=staff_headers
    ).json()
    assert len(msgs) == 1
    assert msgs[0]["sender_type"] == "CUSTOMER"


def test_webhook_thread_reuse(client, staff_headers):
    """OPEN 스레드 존재 시 재사용 — 새 스레드 미생성."""
    resp = _webhook(client, "kakao-key-001", "추가로 정산 일정도 알려주세요")
    assert resp.status_code == 200
    resp = client.get(
        API + "/chat/threads", params={"client_id": S["client_id"]}, headers=staff_headers
    )
    assert resp.json()["total"] == 1  # 스레드 재사용
    msgs = client.get(
        API + "/chat/threads/{0}/messages".format(S["thread_id"]), headers=staff_headers
    ).json()
    assert len(msgs) == 2


def test_webhook_sensitive_keyword_system_message(client, staff_headers):
    """민감 키워드(기본값: 수수료 등) — SYSTEM 메시지 적재."""
    resp = _webhook(client, "kakao-key-001", "저희 계약 수수료가 얼마였죠?")
    assert resp.status_code == 200
    msgs = client.get(
        API + "/chat/threads/{0}/messages".format(S["thread_id"]), headers=staff_headers
    ).json()
    system = [m for m in msgs if m["sender_type"] == "SYSTEM"]
    assert len(system) == 1
    assert "민감 키워드 감지" in system[0]["content"]
    assert "수수료" in system[0]["content"]


def test_webhook_handoff_sets_waiting(client, staff_headers):
    """'담당자' 발화 — WAITING·HUMAN 전환 + 뱃지 카운트."""
    resp = _webhook(client, "kakao-key-001", "담당자 연결 부탁드립니다")
    assert resp.status_code == 200
    assert "담당자" in _simple_text(resp.json())

    resp = client.get(
        API + "/chat/threads", params={"status": "WAITING"}, headers=staff_headers
    )
    waiting = [t for t in resp.json()["items"] if t["thread_id"] == S["thread_id"]]
    assert len(waiting) == 1
    assert waiting[0]["mode"] == "HUMAN"

    resp = client.get(API + "/chat/badge", headers=staff_headers)
    assert resp.status_code == 200
    assert resp.json()["waiting"] >= 1


def test_webhook_handoff_client_extra(client, staff_headers, manager_headers, admin_headers):
    """clientExtra.action=handoff — 발화 무관 WAITING 전환."""
    _webhook(client, "kakao-key-002", "등록 요청")  # PENDING 등록
    resp = client.get(
        API + "/kakao/contacts", params={"status": "PENDING"}, headers=admin_headers
    )
    c2 = [c for c in resp.json()["items"] if c["kakao_user_key"] == "kakao-key-002"][0]
    client.put(
        API + "/kakao/contacts/" + c2["contact_id"],
        headers=manager_headers,
        json={"status": "APPROVED", "client_id": S["client_id"], "name": "이버튼"},
    )
    resp = _webhook(
        client, "kakao-key-002", "버튼으로 연결", client_extra={"action": "handoff"}
    )
    assert resp.status_code == 200
    resp = client.get(
        API + "/chat/threads", params={"status": "WAITING"}, headers=staff_headers
    )
    extra_threads = [t for t in resp.json()["items"] if t["contact_name"] == "이버튼"]
    assert len(extra_threads) == 1
    S["thread2_id"] = extra_threads[0]["thread_id"]


# ---------------------------------------------------------------------------
# 채팅 관제 — 증분 조회·답변·모드 전환·종료
# ---------------------------------------------------------------------------
def test_chat_requires_auth(client):
    assert client.get(API + "/chat/threads").status_code == 401
    assert client.get(API + "/chat/badge").status_code == 401


def test_chat_messages_incremental_after(client, staff_headers):
    url = API + "/chat/threads/{0}/messages".format(S["thread_id"])
    msgs = client.get(url, headers=staff_headers).json()
    assert len(msgs) >= 4
    # created_at 오름차순
    assert msgs == sorted(msgs, key=lambda m: (m["created_at"], m["message_id"]))

    first_id = msgs[0]["message_id"]
    resp = client.get(url, params={"after": first_id}, headers=staff_headers)
    assert resp.status_code == 200
    inc = resp.json()
    assert len(inc) == len(msgs) - 1
    assert first_id not in [m["message_id"] for m in inc]

    # 마지막 메시지 기준 — 신규 없음
    resp = client.get(url, params={"after": msgs[-1]["message_id"]}, headers=staff_headers)
    assert resp.json() == []

    assert (
        client.get(url, params={"after": "no-such-msg"}, headers=staff_headers).status_code == 404
    )
    assert client.get(API + "/chat/threads/no-such/messages", headers=staff_headers).status_code == 404


def test_chat_reply_not_configured(client, staff_headers):
    """Event API 미설정 — delivery=NOT_CONFIGURED, STAFF 메시지는 적재."""
    url = API + "/chat/threads/{0}/messages".format(S["thread_id"])
    before = len(client.get(url, headers=staff_headers).json())

    resp = client.post(
        API + "/chat/threads/{0}/reply".format(S["thread_id"]),
        headers=staff_headers,
        json={"content": "안녕하세요, 확인 후 안내드리겠습니다."},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["delivery"] == "NOT_CONFIGURED"
    assert body["message"]["sender_type"] == "STAFF"
    assert body["message"]["sender_name"] == "실무자"

    msgs = client.get(url, headers=staff_headers).json()
    assert len(msgs) == before + 1  # 발송 불가여도 메시지 적재

    # WAITING → OPEN·HUMAN 전환
    threads = client.get(
        API + "/chat/threads", params={"client_id": S["client_id"]}, headers=staff_headers
    ).json()["items"]
    mine = [t for t in threads if t["thread_id"] == S["thread_id"]][0]
    assert mine["status"] == "OPEN"
    assert mine["mode"] == "HUMAN"


def test_chat_reply_sent_and_failed(client, staff_headers, monkeypatch):
    """Event API 설정 시 — 성공 SENT / 실패 FAILED(메시지는 적재)."""
    monkeypatch.setenv("KAKAO_BOT_ID", "demo-bot")
    monkeypatch.setenv("KAKAO_EVENT_API_KEY", "demo-event-key")
    sent = {}

    def fake_send_event(kakao_user_key, event_name, params=None):
        sent.update({"key": kakao_user_key, "event": event_name, "params": params})
        return {"taskId": "t-1", "status": "SUCCESS"}

    monkeypatch.setattr(kakao_service, "send_event", fake_send_event)
    resp = client.post(
        API + "/chat/threads/{0}/reply".format(S["thread_id"]),
        headers=staff_headers,
        json={"content": "Event API 발송 테스트"},
    )
    assert resp.status_code == 200
    assert resp.json()["delivery"] == "SENT"
    assert sent["key"] == "kakao-key-001"
    assert sent["params"] == {"content": "Event API 발송 테스트"}

    # 발송 실패(비친구 등) — delivery=FAILED, 메시지는 적재
    monkeypatch.setattr(
        kakao_service,
        "send_event",
        lambda **kwargs: (_ for _ in ()).throw(kakao_service.KakaoSendError("not friend")),
    )
    url = API + "/chat/threads/{0}/messages".format(S["thread_id"])
    before = len(client.get(url, headers=staff_headers).json())
    resp = client.post(
        API + "/chat/threads/{0}/reply".format(S["thread_id"]),
        headers=staff_headers,
        json={"content": "실패해도 적재되어야 하는 메시지"},
    )
    assert resp.status_code == 200
    assert resp.json()["delivery"] == "FAILED"
    assert len(client.get(url, headers=staff_headers).json()) == before + 1


def test_chat_thread_close_creates_kakao_activity(client, staff_headers):
    """CLOSED 전환 — tb_activity_history(KAKAO, [자동]) 대화 요약 적재."""
    resp = client.put(
        API + "/chat/threads/" + S["thread_id"],
        headers=staff_headers,
        json={"status": "CLOSED", "assigned_manager_id": "u-manager"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "CLOSED"
    assert body["assigned_manager_name"] == "팀장"

    resp = client.get(
        API + "/histories",
        params={"client_id": S["client_id"], "activity_type": "KAKAO"},
        headers=staff_headers,
    )
    autos = [h for h in resp.json()["items"] if h["is_auto"]]
    assert len(autos) == 1
    assert autos[0]["title"] == "[자동] 카카오 상담: 카카오운수"
    assert "[고객]" in autos[0]["content"]
    assert "[직원]" in autos[0]["content"]

    # 재종료(이미 CLOSED) — 요약 중복 적재 금지
    resp = client.put(
        API + "/chat/threads/" + S["thread_id"], headers=staff_headers, json={"status": "CLOSED"}
    )
    assert resp.status_code == 200
    resp = client.get(
        API + "/histories",
        params={"client_id": S["client_id"], "activity_type": "KAKAO"},
        headers=staff_headers,
    )
    assert len([h for h in resp.json()["items"] if h["is_auto"]]) == 1

    assert (
        client.put(
            API + "/chat/threads/no-such-id", headers=staff_headers, json={"status": "CLOSED"}
        ).status_code
        == 404
    )


def test_chat_threads_search_and_filters(client, staff_headers):
    resp = client.get(API + "/chat/threads", params={"search": "카카오운수"}, headers=staff_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    assert all(t["client_name"] == "카카오운수" for t in resp.json()["items"])

    resp = client.get(API + "/chat/threads", params={"mode": "AI"}, headers=staff_headers)
    assert all(t["mode"] == "AI" for t in resp.json()["items"])

    resp = client.get(API + "/chat/threads", params={"search": "없는회사명"}, headers=staff_headers)
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# 수동 알림톡 (POST /comm/kakao/notify)
# ---------------------------------------------------------------------------
def test_kakao_notify_unconfigured_503(client, staff_headers):
    assert client.post(API + "/comm/kakao/notify", json={"to": "01099990001"}).status_code == 401
    resp = client.post(
        API + "/comm/kakao/notify", headers=staff_headers, json={"to": "01099990001"}
    )
    assert resp.status_code == 503
    assert "SOLAPI_API_KEY" in resp.json()["detail"]


def test_kakao_notify_success(client, staff_headers, monkeypatch):
    monkeypatch.setenv("SOLAPI_API_KEY", "demo-key")
    monkeypatch.setenv("SOLAPI_API_SECRET", "demo-secret")
    monkeypatch.setenv("KAKAO_PF_ID", "demo-pf")
    sent = {}

    def fake_send_alimtalk(to, template_code, variables=None, buttons=None):
        sent.update({"to": to, "template": template_code, "variables": variables})
        return {"groupId": "g-1"}

    monkeypatch.setattr(kakao_service, "send_alimtalk", fake_send_alimtalk)
    resp = client.post(
        API + "/comm/kakao/notify",
        headers=staff_headers,
        json={
            "to": "010-9999-0001",
            "template_code": "TPL_REPLY",
            "variables": {"고객사명": "카카오운수"},
        },
    )
    assert resp.status_code == 200, resp.text
    assert sent["template"] == "TPL_REPLY"
    assert sent["variables"] == {"고객사명": "카카오운수"}


# ---------------------------------------------------------------------------
# 보고서 KAKAO 채널 — BOTH 발송·이메일 단독 폴백 (SCR-12 확장)
# ---------------------------------------------------------------------------
def _prepare_report(client, staff_headers):
    resp = client.post(API + "/reports/generate", headers=staff_headers)
    assert resp.status_code == 200, resp.text
    period = resp.json()["period"]
    rows = client.get(
        API + "/reports", params={"period": period}, headers=staff_headers
    ).json()["items"]
    mine = [r for r in rows if r["client_id"] == S["client_id"]]
    assert len(mine) == 1
    return mine[0]["report_id"]


def _email_ok(monkeypatch):
    monkeypatch.setenv("GMAIL_SENDER", "hooxi12345@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setattr(
        email_service,
        "send_mail",
        lambda **kwargs: {"sender": "hooxi12345@gmail.com", "recipients": kwargs.get("to", [])},
    )


def _alimtalk_env(monkeypatch):
    monkeypatch.setenv("SOLAPI_API_KEY", "demo-key")
    monkeypatch.setenv("SOLAPI_API_SECRET", "demo-secret")
    monkeypatch.setenv("KAKAO_PF_ID", "demo-pf")
    monkeypatch.setenv("KAKAO_TEMPLATE_REPORT", "TPL_REPORT")
    monkeypatch.setenv("APP_BASE_URL", "https://cms.example.com")


def test_send_report_kakao_both(client, staff_headers, monkeypatch):
    """구독 BOTH + APPROVED 연락처(전화 보유) — 알림톡 성공 시 sent_channel=BOTH,
    send_log EMAIL/KAKAO 2행 동일 seq."""
    report_id = _prepare_report(client, staff_headers)
    S["report_id"] = report_id
    resp = client.post(
        API + "/reports/{0}/file".format(report_id),
        headers=staff_headers,
        files={"file": ("kakao_report.pdf", io.BytesIO(b"PDF-KAKAO-V1"), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text

    _email_ok(monkeypatch)
    _alimtalk_env(monkeypatch)
    sent = {}

    def fake_send_alimtalk(to, template_code, variables=None, buttons=None):
        sent.update({"to": to, "template": template_code, "variables": variables, "buttons": buttons})
        return {"groupId": "g-1"}

    monkeypatch.setattr(kakao_service, "send_alimtalk", fake_send_alimtalk)

    resp = client.post(API + "/reports/{0}/send".format(report_id), headers=staff_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["seq"] == 1

    # 알림톡 내용 — 승인 연락처 전화 + 템플릿 변수 + 열람 링크 버튼
    assert sent["to"] == "010-9999-0001"
    assert sent["template"] == "TPL_REPORT"
    assert sent["variables"]["고객사명"] == "카카오운수"
    assert sent["variables"]["보고서유형"] == "월간 운행 보고서"
    link = sent["buttons"][0]["linkMo"]
    assert link.startswith("https://cms.example.com/r/")
    S["view_token"] = link.split("/r/", 1)[1]

    detail = client.get(API + "/reports/" + report_id, headers=staff_headers).json()
    assert detail["status"] == "SENT"
    assert detail["sent_channel"] == "BOTH"
    logs = detail["send_logs"]
    assert len(logs) == 2
    assert {l["channel"] for l in logs} == {"EMAIL", "KAKAO"}
    assert {l["seq"] for l in logs} == {1}  # 채널당 1행, 동일 seq (R2-B2)
    assert all(l["result"] == "SUCCESS" for l in logs)


def test_send_report_kakao_fail_email_fallback(client, staff_headers, monkeypatch):
    """알림톡 실패 — 이메일 성공이면 SENT 유지 + sent_channel=EMAIL(단독 폴백) + KAKAO FAIL 행."""
    _email_ok(monkeypatch)
    _alimtalk_env(monkeypatch)
    monkeypatch.setattr(
        kakao_service,
        "send_alimtalk",
        lambda **kwargs: (_ for _ in ()).throw(kakao_service.KakaoSendError("SOLAPI 400")),
    )

    resp = client.post(API + "/reports/{0}/send".format(S["report_id"]), headers=staff_headers)
    assert resp.status_code == 200, resp.text  # 이메일 성공 — 알림톡 실패는 발송을 막지 않음
    assert resp.json()["seq"] == 2

    detail = client.get(API + "/reports/" + S["report_id"], headers=staff_headers).json()
    assert detail["status"] == "SENT"
    assert detail["sent_channel"] == "EMAIL"  # BOTH 아님 — 이메일 단독
    seq2 = [l for l in detail["send_logs"] if l["seq"] == 2]
    assert len(seq2) == 2
    results = {l["channel"]: l["result"] for l in seq2}
    assert results == {"EMAIL": "SUCCESS", "KAKAO": "FAIL"}


# ---------------------------------------------------------------------------
# 열람 페이지 — GET /r/{token} (무인증, 루트 경로)
# ---------------------------------------------------------------------------
def test_view_report_page(client):
    resp = client.get("/r/" + S["view_token"])
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/html")
    assert "카카오운수" in resp.text
    assert "다운로드" in resp.text

    # 열람 추적 — tb_audit_log(REPORT_VIEW) 적재
    db = models.SessionLocal()
    try:
        views = (
            db.query(models.AuditLog)
            .filter(
                models.AuditLog.action == "REPORT_VIEW",
                models.AuditLog.target_id == S["report_id"],
            )
            .all()
        )
        assert len(views) == 1
    finally:
        db.close()


def test_view_report_file_stream(client):
    """로컬 저장소 폴백 — 토큰 재검증 스트림 엔드포인트."""
    resp = client.get("/r/{0}/file".format(S["view_token"]))
    assert resp.status_code == 200
    assert resp.content == b"PDF-KAKAO-V1"
    assert "attachment" in resp.headers["content-disposition"]


def test_view_token_expired_and_invalid(client):
    expired = pyjwt.encode(
        {
            "type": "view",
            "doc_id": "x",
            "report_id": "y",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        "test",
        algorithm="HS256",
    )
    resp = client.get("/r/" + expired)
    assert resp.status_code == 410  # 만료 안내 HTML
    assert "만료" in resp.text

    resp = client.get("/r/not-a-token")
    assert resp.status_code == 401

    # type이 view가 아닌 토큰 거부
    wrong_type = pyjwt.encode(
        {
            "type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "test",
        algorithm="HS256",
    )
    assert client.get("/r/" + wrong_type).status_code == 401
    assert client.get("/r/{0}/file".format(expired)).status_code == 410
