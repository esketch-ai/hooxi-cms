"""P1 전 엔드포인트 스모크 테스트 — 정상 경로 + 인증/RBAC 거부 + 404 + 발송 미설정 503.

테스트는 파일 내 선언 순서대로 실행되며 세션 픽스처(임시 SQLite)를 공유한다.
"""

import io

import pytest

from services import email_service

API = "/api/v1"
S = {}  # 테스트 간 공유 상태 (생성된 리소스 id)


# ---------------------------------------------------------------------------
# 기반: health · 인증 · RBAC
# ---------------------------------------------------------------------------
def test_health(client):
    resp = client.get(API + "/health")
    assert resp.status_code == 200
    assert resp.json()["database_available"] is True


@pytest.mark.parametrize(
    "path",
    [
        "/clients",
        "/histories",
        "/schedules",
        "/reports",
        "/documents",
        "/dashboard/stats",
    ],
)
def test_auth_required(client, path):
    """모든 P1 엔드포인트는 인증 필수 — 미인증 401."""
    assert client.get(API + path).status_code == 401


def test_write_requires_auth(client):
    assert client.post(API + "/clients", json={}).status_code == 401
    assert client.post(API + "/reports/generate").status_code == 401


def test_rbac_staff_forbidden_on_manager_endpoint(client, staff_headers):
    """§10.1 — 사용자 목록은 MANAGER 이상. STAFF는 403."""
    assert client.get(API + "/users", headers=staff_headers).status_code == 403


def test_pending_user_cannot_login(client):
    resp = client.post(
        API + "/auth/dev-login", json={"email": "pending@hooxipartners.com"}
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 고객사 (SCR-03/03D)
# ---------------------------------------------------------------------------
def test_create_client_with_subscription(client, staff_headers):
    resp = client.post(
        API + "/clients",
        headers=staff_headers,
        json={
            "client_type": "TRANSPORT",
            "company_name": "테스트운수",
            "biz_reg_no": "111-22-33333",
            "main_contact_name": "김담당",
            "main_contact_email": "contact@test-transport.example.com",
            "contract_status": "ACTIVE",
            "manager_id": "u-manager",
            "report_yn": "Y",
            "subscription": {"report_type": "월간 운행 보고서", "channel": "EMAIL", "due_day": 25},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["company_name"] == "테스트운수"
    assert body["manager_name"] == "팀장"
    assert len(body["subscriptions"]) == 1
    assert body["subscriptions"][0]["due_day"] == 25
    S["client_id"] = body["client_id"]


def test_create_client_invalid_type_rejected(client, staff_headers):
    resp = client.post(
        API + "/clients",
        headers=staff_headers,
        json={"client_type": "WRONG", "company_name": "x"},
    )
    assert resp.status_code == 422


def test_list_clients_filters_and_badge(client, staff_headers):
    resp = client.get(API + "/clients", headers=staff_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1

    resp = client.get(
        API + "/clients",
        params={"client_type": "TRANSPORT", "search": "테스트운수"},
        headers=staff_headers,
    )
    body = resp.json()
    assert body["total"] == 1
    item = body["items"][0]
    # 목록 전용 필드 존재 (이번 달 보고서 미니 배지·최근 활동)
    assert "report_status_this_month" in item
    assert "last_activity_at" in item

    resp = client.get(API + "/clients", params={"client_type": "FACILITY"}, headers=staff_headers)
    assert all(i["client_type"] == "FACILITY" for i in resp.json()["items"])


def test_get_client_detail_and_404(client, staff_headers):
    resp = client.get(API + "/clients/" + S["client_id"], headers=staff_headers)
    assert resp.status_code == 200
    assert resp.json()["subscriptions"][0]["report_type"] == "월간 운행 보고서"
    assert client.get(API + "/clients/no-such-id", headers=staff_headers).status_code == 404


def test_update_client_and_subscription_upsert(client, staff_headers):
    resp = client.put(
        API + "/clients/" + S["client_id"],
        headers=staff_headers,
        json={"keyman": "박이사", "subscription": {"report_type": "월간 운행 보고서", "due_day": 20}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["keyman"] == "박이사"
    assert len(body["subscriptions"]) == 1  # 동일 유형 upsert — 중복 생성 금지
    assert body["subscriptions"][0]["due_day"] == 20


def test_client_subresources(client, staff_headers):
    for sub in ("histories", "reports", "documents", "assets", "projects"):
        resp = client.get(
            "{0}/clients/{1}/{2}".format(API, S["client_id"], sub), headers=staff_headers
        )
        assert resp.status_code == 200, sub
        assert isinstance(resp.json(), list)
    assert (
        client.get(API + "/clients/no-such-id/histories", headers=staff_headers).status_code == 404
    )


# ---------------------------------------------------------------------------
# 활동 이력·이슈 (SCR-05/02)
# ---------------------------------------------------------------------------
def test_create_history_call(client, staff_headers):
    resp = client.post(
        API + "/histories",
        headers=staff_headers,
        json={
            "client_id": S["client_id"],
            "activity_date": "2026-07-01T10:00:00",
            "activity_type": "CALL",
            "retention_stage": "활용",
            "issue_status": "OPEN",  # ISSUE 외 유형 — 서버에서 무시되어야 함
            "title": "정기 안부 콜",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["issue_status"] is None  # 이슈 전용 필드 미저장
    assert body["created_by"] == "u-staff"
    assert body["manager_id"] == "u-staff"  # 미지정 시 현재 사용자
    assert body["is_auto"] is False
    S["call_history_id"] = body["history_id"]


def test_create_history_issue_defaults(client, staff_headers):
    resp = client.post(
        API + "/histories",
        headers=staff_headers,
        json={
            "client_id": S["client_id"],
            "activity_date": "2026-07-05T09:00:00",
            "activity_type": "ISSUE",
            "priority": "URGENT",
            "due_date": "2026-07-15",
            "title": "데이터 연동 오류",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["issue_status"] == "OPEN"  # 기본값
    assert body["priority"] == "URGENT"
    S["issue_history_id"] = body["history_id"]


def test_list_histories_filters(client, staff_headers):
    resp = client.get(
        API + "/histories",
        params={"activity_type": "ISSUE", "client_id": S["client_id"]},
        headers=staff_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert all(i["activity_type"] == "ISSUE" for i in body["items"])

    resp = client.get(API + "/histories", params={"created_by": "u-staff"}, headers=staff_headers)
    assert resp.json()["total"] >= 2

    resp = client.get(
        API + "/histories",
        params={"date_from": "2026-07-05", "date_to": "2026-07-05"},
        headers=staff_headers,
    )
    assert all(i["activity_date"].startswith("2026-07-05") for i in resp.json()["items"])


def test_list_histories_search(client, staff_headers):
    """서버 검색 — 고객사명·제목 부분일치(outerjoin), total 정확성, 페이지 밖 항목 히트."""
    # 고객 미지정 이력 — outerjoin이라 검색어 없을 때 누락되면 안 되고, 제목으로도 히트해야 함
    resp = client.post(
        API + "/histories",
        headers=staff_headers,
        json={
            "activity_date": "2026-07-03T14:00:00",
            "activity_type": "MEETING",
            "title": "미지정검색 내부 회의",
        },
    )
    assert resp.status_code == 201

    # 고객사명 부분일치 — 해당 고객사의 이력만 히트
    resp = client.get(API + "/histories", params={"search": "테스트운"}, headers=staff_headers)
    body = resp.json()
    assert body["total"] == 2  # CALL + ISSUE (미지정 이력 제외)
    assert all(i["client_id"] == S["client_id"] for i in body["items"])

    # 제목 부분일치 — client_id 없는 이력도 히트 (outerjoin)
    resp = client.get(API + "/histories", params={"search": "미지정검색"}, headers=staff_headers)
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["client_id"] is None

    # 검색어 없으면 미지정 고객 이력도 누락 없이 포함
    resp = client.get(API + "/histories", headers=staff_headers)
    assert any(i["client_id"] is None for i in resp.json()["items"])

    # 미스 — 0건, total 0
    resp = client.get(API + "/histories", params={"search": "없는검색어zz"}, headers=staff_headers)
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []

    # 1페이지에 없는 항목이 검색으로 히트 — page_size=1이면 최신순 1페이지는 ISSUE(07-05)뿐
    resp = client.get(API + "/histories", params={"page_size": 1}, headers=staff_headers)
    assert all("안부" not in (i["title"] or "") for i in resp.json()["items"])
    resp = client.get(
        API + "/histories", params={"page_size": 1, "search": "안부"}, headers=staff_headers
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "정기 안부 콜"


def test_issue_status_change_kanban(client, staff_headers):
    resp = client.put(
        API + "/histories/{0}/status".format(S["issue_history_id"]),
        headers=staff_headers,
        json={"issue_status": "IN_PROGRESS", "comment": "담당 배정 완료"},
    )
    assert resp.status_code == 200
    assert resp.json()["issue_status"] == "IN_PROGRESS"

    # 상태 변경이 코멘트 스레드에 자동 적재 (GAN A4)
    resp = client.get(
        API + "/histories/{0}/comments".format(S["issue_history_id"]), headers=staff_headers
    )
    logs = [c for c in resp.json() if c["comment_type"] == "STATUS_CHANGE"]
    assert len(logs) == 1
    assert "OPEN → IN_PROGRESS" in logs[0]["content"]
    assert "담당 배정 완료" in logs[0]["content"]


def test_issue_status_change_rejected_for_non_issue(client, staff_headers):
    resp = client.put(
        API + "/histories/{0}/status".format(S["call_history_id"]),
        headers=staff_headers,
        json={"issue_status": "CLOSED"},
    )
    assert resp.status_code == 409


def test_issue_status_404(client, staff_headers):
    resp = client.put(
        API + "/histories/no-such-id/status",
        headers=staff_headers,
        json={"issue_status": "CLOSED"},
    )
    assert resp.status_code == 404


def test_comments_thread(client, staff_headers):
    resp = client.post(
        API + "/histories/{0}/comments".format(S["issue_history_id"]),
        headers=staff_headers,
        json={"content": "고객사에 원인 공유함"},
    )
    assert resp.status_code == 201
    assert resp.json()["manager_name"] == "실무자"

    resp = client.get(
        API + "/histories/{0}/comments".format(S["issue_history_id"]), headers=staff_headers
    )
    assert len(resp.json()) == 2  # STATUS_CHANGE + COMMENT
    assert client.get(API + "/histories/no-such-id/comments", headers=staff_headers).status_code == 404


# ---------------------------------------------------------------------------
# 일정 (SCR-11)
# ---------------------------------------------------------------------------
def test_create_schedule(client, staff_headers):
    resp = client.post(
        API + "/schedules",
        headers=staff_headers,
        json={
            "client_id": S["client_id"],
            "schedule_type": "MEETING",
            "title": "월간 리뷰 미팅",
            "start_at": "2026-07-20T14:00:00",
            "end_at": "2026-07-20T15:00:00",
            "location": "고객사 본사",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "PLANNED"
    assert body["manager_id"] == "u-staff"
    S["schedule_id"] = body["schedule_id"]


def test_list_schedules_month_and_filters(client, staff_headers):
    resp = client.get(API + "/schedules", params={"month": "2026-07"}, headers=staff_headers)
    assert resp.status_code == 200
    assert any(s["schedule_id"] == S["schedule_id"] for s in resp.json())

    resp = client.get(API + "/schedules", params={"month": "2026-08"}, headers=staff_headers)
    assert all(s["schedule_id"] != S["schedule_id"] for s in resp.json())

    resp = client.get(API + "/schedules", params={"month": "2026-13"}, headers=staff_headers)
    assert resp.status_code == 422

    resp = client.get(
        API + "/schedules", params={"schedule_type": "MEETING"}, headers=staff_headers
    )
    assert all(s["schedule_type"] == "MEETING" for s in resp.json())


def test_schedule_drag_date_change(client, staff_headers):
    resp = client.put(
        API + "/schedules/" + S["schedule_id"],
        headers=staff_headers,
        json={"start_at": "2026-07-22T14:00:00", "end_at": "2026-07-22T15:00:00"},
    )
    assert resp.status_code == 200
    assert resp.json()["start_at"].startswith("2026-07-22")


def test_schedule_done_creates_auto_history(client, staff_headers):
    resp = client.put(
        API + "/schedules/" + S["schedule_id"],
        headers=staff_headers,
        json={"status": "DONE", "result_note": "재계약 조건 합의"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "DONE"
    assert body["history_id"]  # 자동 적재된 활동 이력 연결

    resp = client.get(
        API + "/histories", params={"client_id": S["client_id"]}, headers=staff_headers
    )
    auto = [h for h in resp.json()["items"] if h["history_id"] == body["history_id"]]
    assert len(auto) == 1
    assert auto[0]["is_auto"] is True  # "자동" 표식
    assert auto[0]["title"].startswith("[자동]")
    assert auto[0]["content"] == "재계약 조건 합의"
    assert auto[0]["activity_type"] == "MEETING"


def test_schedule_404(client, staff_headers):
    resp = client.put(
        API + "/schedules/no-such-id", headers=staff_headers, json={"status": "DONE"}
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 월간 보고서 발송 (SCR-12)
# ---------------------------------------------------------------------------
def test_generate_reports_idempotent(client, staff_headers):
    resp = client.post(API + "/reports/generate", headers=staff_headers)
    assert resp.status_code == 200, resp.text
    first = resp.json()
    assert first["created"] >= 1
    S["period"] = first["period"]

    # 멱등 — 재실행 시 중복 생성 금지
    resp = client.post(
        API + "/reports/generate", params={"period": first["period"]}, headers=staff_headers
    )
    second = resp.json()
    assert second["created"] == 0
    assert second["skipped"] >= 1

    # 마감일 REPORT_DUE 일정 자동 생성 (SCR-11 연동)
    resp = client.get(
        API + "/schedules",
        params={"schedule_type": "REPORT_DUE", "client_id": S["client_id"]},
        headers=staff_headers,
    )
    assert len(resp.json()) == 1


def test_generate_invalid_period(client, staff_headers):
    resp = client.post(
        API + "/reports/generate", params={"period": "2026/07"}, headers=staff_headers
    )
    assert resp.status_code == 422


def test_list_reports_with_summary(client, staff_headers):
    resp = client.get(API + "/reports", params={"period": S["period"]}, headers=staff_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["target"] >= 1
    assert body["summary"]["standby"] >= 1
    mine = [i for i in body["items"] if i["client_id"] == S["client_id"]]
    assert len(mine) == 1
    assert mine[0]["client_name"] == "테스트운수"
    assert mine[0]["due_date"].endswith("-20")  # 구독 due_day=20 반영
    S["report_id"] = mine[0]["report_id"]


def test_upload_report_file_versioning(client, staff_headers):
    resp = client.post(
        API + "/reports/{0}/file".format(S["report_id"]),
        headers=staff_headers,
        files={"file": ("report_v1.pdf", io.BytesIO(b"PDF-DEMO-V1"), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["version"] == 1
    assert resp.json()["doc_type"] == "REPORT"

    # 상태 STANDBY → WRITING 전환
    resp = client.get(API + "/reports/" + S["report_id"], headers=staff_headers)
    assert resp.json()["status"] == "WRITING"

    # 버전 적재
    resp = client.post(
        API + "/reports/{0}/file".format(S["report_id"]),
        headers=staff_headers,
        files={"file": ("report_v2.pdf", io.BytesIO(b"PDF-DEMO-V2"), "application/pdf")},
    )
    assert resp.json()["version"] == 2


def test_send_report_unconfigured_503(client, staff_headers):
    """Gmail 미설정 — 503 + 명확한 한국어 메시지 + 상태 변경 없음."""
    resp = client.post(API + "/reports/{0}/send".format(S["report_id"]), headers=staff_headers)
    assert resp.status_code == 503
    assert "GMAIL_SENDER" in resp.json()["detail"]

    detail = client.get(API + "/reports/" + S["report_id"], headers=staff_headers).json()
    assert detail["status"] == "WRITING"  # 상태 유지
    assert detail["send_logs"] == []  # 로그 미적재


def test_send_report_smtp_failure_502(client, staff_headers, monkeypatch):
    """SMTP 실패 — 직전 상태 유지 + FAIL 회차 기록 + 502."""
    monkeypatch.setenv("GMAIL_SENDER", "hooxi12345@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setattr(
        email_service, "send_mail", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("SMTP down"))
    )
    resp = client.post(API + "/reports/{0}/send".format(S["report_id"]), headers=staff_headers)
    assert resp.status_code == 502

    detail = client.get(API + "/reports/" + S["report_id"], headers=staff_headers).json()
    assert detail["status"] == "WRITING"
    assert len(detail["send_logs"]) == 1
    assert detail["send_logs"][0]["result"] == "FAIL"


def test_send_report_success(client, staff_headers, monkeypatch):
    """발송 성공 — SENT + send_log(SUCCESS, 새 seq) + 활동 이력 EMAIL [자동] 적재."""
    monkeypatch.setenv("GMAIL_SENDER", "hooxi12345@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    sent = {}

    def fake_send_mail(to, subject, body, cc=None, attachments=None, reply_to=None, html=False):
        sent.update({"to": to, "subject": subject, "attachments": attachments, "reply_to": reply_to})
        return {"sender": "hooxi12345@gmail.com", "recipients": list(to) + list(cc or [])}

    monkeypatch.setattr(email_service, "send_mail", fake_send_mail)

    resp = client.post(API + "/reports/{0}/send".format(S["report_id"]), headers=staff_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["seq"] == 2  # FAIL 다음 새 회차 (R2-B3)
    # 수신자 폴백: 등록 수신자 없음 → main_contact_email (R2-B5)
    assert body["recipients"] == ["contact@test-transport.example.com"]
    assert sent["attachments"][0][1] == b"PDF-DEMO-V2"  # 최신 버전 첨부
    assert sent["reply_to"] == "manager@hooxipartners.com"  # 담당 PM 회신 주소 (CR-2)

    detail = client.get(API + "/reports/" + S["report_id"], headers=staff_headers).json()
    assert detail["status"] == "SENT"
    assert detail["sent_channel"] == "EMAIL"
    assert len(detail["send_logs"]) == 2
    assert detail["send_logs"][0]["result"] == "SUCCESS"  # seq 역순 정렬

    # 활동 이력 EMAIL 자동 적재
    resp = client.get(
        API + "/histories",
        params={"client_id": S["client_id"], "activity_type": "EMAIL"},
        headers=staff_headers,
    )
    autos = [h for h in resp.json()["items"] if h["is_auto"]]
    assert len(autos) == 1
    assert "보고서 이메일 발송" in autos[0]["title"]


def test_report_detail_expansion(client, staff_headers):
    resp = client.get(API + "/reports/" + S["report_id"], headers=staff_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert [d["version"] for d in body["documents"]] == [2, 1]  # 버전 히스토리 역순
    assert body["latest_doc"]["version"] == 2
    assert body["comments"] == []
    assert client.get(API + "/reports/no-such-id", headers=staff_headers).status_code == 404


def test_report_status_confirmed_and_cancel_validation(client, staff_headers):
    resp = client.put(
        API + "/reports/{0}/status".format(S["report_id"]),
        headers=staff_headers,
        json={"status": "CONFIRMED", "confirm_basis": "회신메일"},
    )
    assert resp.status_code == 200
    assert resp.json()["confirmed_at"] is not None
    assert resp.json()["confirm_basis"] == "회신메일"

    # 취소는 사유 필수 (R3-3)
    resp = client.put(
        API + "/reports/{0}/status".format(S["report_id"]),
        headers=staff_headers,
        json={"status": "CANCELED"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 문서 아카이브 (SCR-13)
# ---------------------------------------------------------------------------
def test_upload_document(client, staff_headers):
    resp = client.post(
        API + "/documents",
        headers=staff_headers,
        data={"doc_type": "CONTRACT", "title": "운영 계약서", "client_id": S["client_id"]},
        files={"file": ("contract.pdf", io.BytesIO(b"CONTRACT-BYTES"), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["doc_type"] == "CONTRACT"
    assert body["client_name"] == "테스트운수"
    S["doc_id"] = body["doc_id"]


def test_upload_document_invalid_type(client, staff_headers):
    resp = client.post(
        API + "/documents",
        headers=staff_headers,
        data={"doc_type": "WRONG"},
        files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
    )
    assert resp.status_code == 422


def test_list_documents_filters(client, staff_headers):
    resp = client.get(
        API + "/documents",
        params={"client_id": S["client_id"], "doc_type": "CONTRACT"},
        headers=staff_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == S["doc_id"]

    # 보고서 업로드 파일은 REPORT로 자동 분류 적재
    resp = client.get(
        API + "/documents",
        params={"client_id": S["client_id"], "doc_type": "REPORT"},
        headers=staff_headers,
    )
    assert resp.json()["total"] == 2


def test_download_document(client, staff_headers):
    resp = client.get(
        API + "/documents/{0}/download".format(S["doc_id"]), headers=staff_headers
    )
    assert resp.status_code == 200
    assert resp.content == b"CONTRACT-BYTES"
    assert (
        client.get(API + "/documents/no-such-id/download", headers=staff_headers).status_code
        == 404
    )


def test_upload_document_sign_and_history_filter(client, staff_headers):
    """태블릿 현장 서명 — SIGN 유형은 서명 폴더로 저장, history_id로 조회."""
    resp = client.post(
        API + "/documents",
        headers=staff_headers,
        data={
            "doc_type": "SIGN",
            "title": "현장 확인 서명",
            "client_id": S["client_id"],
            "history_id": S["call_history_id"],
        },
        files={"file": ("sign.png", io.BytesIO(b"SIGN-BYTES"), "image/png")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["doc_type"] == "SIGN"
    assert "/서명/" in body["file_url"]  # 업체별 서명 폴더 규칙
    sign_doc_id = body["doc_id"]

    # history_id 필터 — 해당 활동 이력에 연결된 문서만
    resp = client.get(
        API + "/documents",
        params={"history_id": S["call_history_id"]},
        headers=staff_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == sign_doc_id


def test_upload_document_asset_link_and_filter(client, staff_headers):
    """자산별 사진(제원표 등) — asset_id 연결 저장, asset_id로 역조회."""
    import models

    db = models.SessionLocal()
    try:
        db.add(
            models.Asset(
                asset_id="a-doc-test",
                client_id=S["client_id"],
                asset_group="MOBILITY",
                asset_type="EV",
                main_spec="현대 일렉시티",
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.post(
        API + "/documents",
        headers=staff_headers,
        data={
            "doc_type": "PHOTO",
            "title": "제원표_현대 일렉시티_20260715",
            "client_id": S["client_id"],
            "asset_id": "a-doc-test",
        },
        files={"file": ("spec.jpg", io.BytesIO(b"SPEC-BYTES"), "image/jpeg")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["asset_id"] == "a-doc-test"
    asset_doc_id = body["doc_id"]

    # asset_id 필터 — 해당 자산에 연결된 문서만
    resp = client.get(
        API + "/documents",
        params={"asset_id": "a-doc-test"},
        headers=staff_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == asset_doc_id


def test_upload_document_asset_404(client, staff_headers):
    """존재하지 않는 asset_id 업로드는 404."""
    resp = client.post(
        API + "/documents",
        headers=staff_headers,
        data={"doc_type": "PHOTO", "asset_id": "no-such-asset"},
        files={"file": ("x.jpg", io.BytesIO(b"x"), "image/jpeg")},
    )
    assert resp.status_code == 404


def test_delete_asset_detaches_photos(client, admin_headers, staff_headers):
    """자산 삭제 시 연결 사진은 보존되고 asset_id 참조만 해제된다(FK 위반·고아 참조 방지)."""
    import models

    db = models.SessionLocal()
    try:
        db.add(
            models.Asset(
                asset_id="a-del-test",
                client_id=S["client_id"],
                asset_group="MOBILITY",
                asset_type="EV",
                main_spec="삭제 테스트 차량",
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.post(
        API + "/documents",
        headers=staff_headers,
        data={
            "doc_type": "PHOTO",
            "title": "제원표_삭제 테스트 차량_20260715",
            "client_id": S["client_id"],
            "asset_id": "a-del-test",
        },
        files={"file": ("spec.jpg", io.BytesIO(b"SPEC"), "image/jpeg")},
    )
    assert resp.status_code == 201, resp.text
    doc_id = resp.json()["doc_id"]

    resp = client.delete(API + "/assets/a-del-test", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    # 사진은 문서함에 남고 자산 참조만 해제
    db = models.SessionLocal()
    try:
        doc = db.query(models.Document).filter(models.Document.doc_id == doc_id).one()
        assert doc.asset_id is None
    finally:
        db.close()


def test_upload_document_over_size_limit(client, staff_headers):
    """25MB 초과 업로드는 413."""
    big = b"x" * (25 * 1024 * 1024 + 1)
    resp = client.post(
        API + "/documents",
        headers=staff_headers,
        data={"doc_type": "ETC"},
        files={"file": ("big.bin", io.BytesIO(big), "application/octet-stream")},
    )
    assert resp.status_code == 413


# ---------------------------------------------------------------------------
# 대시보드 (SCR-01)
# ---------------------------------------------------------------------------
def test_dashboard_stats(client, staff_headers):
    resp = client.get(API + "/dashboard/stats", headers=staff_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    kpi = body["kpi"]
    assert kpi["total_clients"] >= 1
    assert kpi["report_target"] >= 1
    assert kpi["report_sent"] >= 1  # CONFIRMED 포함
    assert kpi["urgent_open_issues"] >= 1  # URGENT ISSUE(IN_PROGRESS) 잔존
    assert kpi["expected_billing_amount"] is None  # 정산 매핑 없음 → 미정

    # §10.2 기본 퍼널 4단계
    assert [f["stage"] for f in body["funnel"]] == ["관심/접촉", "제안/검토", "계약 진행", "온보딩/활성"]
    funnel = {f["stage"]: f["count"] for f in body["funnel"]}
    assert funnel["온보딩/활성"] >= 1  # retention_stage=활용

    assert 0 < len(body["recent_activities"]) <= 20
    assert all("created_by_name" in h for h in body["recent_activities"])
    assert all(i["issue_status"] != "CLOSED" for i in body["open_issues"])


def test_dashboard_funnel_config_override(client, staff_headers):
    """tb_config funnel_mapping 오버라이드 존중."""
    import json as _json

    import models

    db = models.SessionLocal()
    try:
        db.add(
            models.Config(
                config_key="funnel_mapping",
                config_value=_json.dumps({"전체": ["인지", "관심", "검토", "구매결정", "온보딩", "활용", "재계약", "확장"]}),
                description="테스트 오버라이드",
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.get(API + "/dashboard/stats", headers=staff_headers)
    body = resp.json()
    assert [f["stage"] for f in body["funnel"]] == ["전체"]
    assert body["funnel"][0]["count"] >= 1


def test_dashboard_expected_billing_current_month_only(client, staff_headers):
    """당월 예상 청구액 — 정산 기준월(_period_of) 당월분만 합산 (감사 지적 4).

    - STANDBY(예상 발급월=당월) + BILLED(billed_at=당월) → 합산
    - 타월 STANDBY / 당월 COMPLETED → 제외
    """
    import datetime as _dt

    import models

    period = client.get(API + "/dashboard/stats", headers=staff_headers).json()["period"]
    year, month = int(period[:4]), int(period[5:7])
    in_month = _dt.datetime(year, month, 15)
    prev = _dt.datetime(year - 1, 12, 15) if month == 1 else _dt.datetime(year, month - 1, 15)

    db = models.SessionLocal()
    try:
        # uq_project_client_map_slot — (사업, 고객사) 조합은 매핑 1건씩만 (F2)
        c = models.Client(client_type="TRANSPORT", company_name="정산당월테스트사")
        c2 = models.Client(client_type="TRANSPORT", company_name="정산당월테스트사2")
        p_now = models.Project(project_name="당월발급사업", project_status="모니터링",
                               expected_issue_date=in_month.date())
        p_prev = models.Project(project_name="타월발급사업", project_status="모니터링",
                                expected_issue_date=prev.date())
        db.add_all([c, c2, p_now, p_prev])
        db.flush()
        maps = [
            # 당월 포함분: STANDBY(예상 발급월) 1000 + BILLED(billed_at) 200
            models.ProjectClientMap(project_id=p_now.project_id, client_id=c.client_id,
                                    settlement_status="STANDBY", expected_amount=1000),
            models.ProjectClientMap(project_id=p_prev.project_id, client_id=c.client_id,
                                    settlement_status="BILLED", billed_at=in_month,
                                    expected_amount=200),
            # 제외분: 타월 STANDBY / 당월 COMPLETED — 다른 고객사로 슬롯 분리
            models.ProjectClientMap(project_id=p_prev.project_id, client_id=c2.client_id,
                                    settlement_status="STANDBY", expected_amount=99999),
            models.ProjectClientMap(project_id=p_now.project_id, client_id=c2.client_id,
                                    settlement_status="COMPLETED", billed_at=in_month,
                                    completed_at=in_month, expected_amount=77777),
        ]
        db.add_all(maps)
        db.commit()
        map_ids = [m.map_id for m in maps]
        seeded = (c.client_id, p_now.project_id, p_prev.project_id)
    finally:
        db.close()

    try:
        kpi = client.get(API + "/dashboard/stats", headers=staff_headers).json()["kpi"]
        assert kpi["expected_billing_amount"] == 1200.0
    finally:
        # 후속 테스트(정산 등) 오염 방지 — 시딩분 정리
        db = models.SessionLocal()
        try:
            db.query(models.ProjectClientMap).filter(
                models.ProjectClientMap.map_id.in_(map_ids)
            ).delete(synchronize_session=False)
            db.query(models.Project).filter(
                models.Project.project_id.in_(seeded[1:])
            ).delete(synchronize_session=False)
            db.query(models.Client).filter(models.Client.client_id == seeded[0]).delete()
            db.commit()
        finally:
            db.close()
