"""보고서 운영 보강 (P1-F) — 고정본 지정·업로드 감사·파일 소실 발송 409.

검증 포인트:
- PUT /reports/{id}/pin: 고정본 지정 → 발송 파일 선정이 pinned 우선(첨부 파일명 검증)
- 타 보고서 문서 지정 422 / SENT·CANCELED 등 종결 상태 409 / null 해제 → 최신본 복귀
- 고정/해제 감사 REPORT_PIN(new_value "v1 고정"/"고정 해제")
- 보고서 파일 업로드 감사 DOCUMENT_UPLOAD 적재 (documents.py와 동일 관용구)
- 저장소 파일 소실 시 발송 409 (500 아님 — 프론트 '서버 오류' 오인 방지)
"""

import io
import os

import models
from services import email_service

API = "/api/v1"
PERIOD = "2027-05"  # 타 테스트 모듈과 겹치지 않는 전용 기간
S = {}  # 테스트 간 공유 상태 (생성된 리소스 id)


def _create_client(client, headers, name, email):
    resp = client.post(
        API + "/clients",
        headers=headers,
        json={
            "client_type": "TRANSPORT",
            "company_name": name,
            "contract_status": "ACTIVE",
            "report_yn": "Y",
            "main_contact_email": email,
            "subscription": {"report_type": "월간 운행 보고서", "channel": "EMAIL", "due_day": 25},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["client_id"]


def _report_of(client, headers, client_id):
    resp = client.get(API + "/reports", params={"period": PERIOD}, headers=headers)
    assert resp.status_code == 200, resp.text
    mine = [i for i in resp.json()["items"] if i["client_id"] == client_id]
    assert len(mine) == 1
    return mine[0]


def _upload(client, headers, report_id, filename):
    resp = client.post(
        API + "/reports/{0}/file".format(report_id),
        headers=headers,
        files={"file": (filename, io.BytesIO(b"PDF-PIN-" + filename.encode()), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _pin(client, headers, report_id, doc_id):
    return client.put(
        API + "/reports/{0}/pin".format(report_id),
        headers=headers,
        json={"doc_id": doc_id},
    )


def _send_and_capture(client, headers, report_id, monkeypatch):
    """send_mail 모킹으로 첨부 파일명 캡처 — 발송 성공 200 확인 (mail_template 테스트 관용구)."""
    monkeypatch.setenv("GMAIL_SENDER", "hooxi12345@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    sent = {}

    def fake_send_mail(to, subject, body, cc=None, attachments=None, reply_to=None, html=False):
        sent.update({"to": to, "attachments": attachments})
        return {"sender": "hooxi12345@gmail.com", "recipients": list(to) + list(cc or [])}

    monkeypatch.setattr(email_service, "send_mail", fake_send_mail)
    resp = client.post(API + "/reports/{0}/send".format(report_id), headers=headers)
    assert resp.status_code == 200, resp.text
    return sent


def test_setup_reports_and_files(client, staff_headers):
    S["main"] = _create_client(client, staff_headers, "고정본운수", "pin-main@pin.example.com")
    S["other"] = _create_client(client, staff_headers, "고정본타사운수", "pin-other@pin.example.com")
    S["lost"] = _create_client(client, staff_headers, "파일소실운수", "pin-lost@pin.example.com")
    resp = client.post(
        API + "/reports/generate", params={"period": PERIOD}, headers=staff_headers
    )
    assert resp.status_code == 200, resp.text

    for key in ("main", "other", "lost"):
        S[key + "_report"] = _report_of(client, staff_headers, S[key])["report_id"]

    # main: v1·v2 업로드(doc_id는 최신 v2), other: 1건 (422 교차 지정용)
    S["main_v1"] = _upload(client, staff_headers, S["main_report"], "report-v1.pdf")
    S["main_v2"] = _upload(client, staff_headers, S["main_report"], "report-v2.pdf")
    S["other_v1"] = _upload(client, staff_headers, S["other_report"], "other-v1.pdf")
    assert S["main_v1"]["version"] == 1 and S["main_v2"]["version"] == 2


def test_upload_audit_recorded(client, staff_headers):
    """업로드 감사 DOCUMENT_UPLOAD — 문서명 수준만 기록 (R2-E6, documents.py 관용구)."""
    db = models.SessionLocal()
    try:
        row = (
            db.query(models.AuditLog)
            .filter(
                models.AuditLog.action == "DOCUMENT_UPLOAD",
                models.AuditLog.target_id == S["main_v2"]["doc_id"],
            )
            .first()
        )
        assert row is not None
        assert row.target_type == "DOCUMENT"
        assert "report-v2.pdf" in (row.new_value or "")
        assert "(v2)" in (row.new_value or "")
    finally:
        db.close()


def test_pin_v1_and_audit(client, staff_headers):
    resp = _pin(client, staff_headers, S["main_report"], S["main_v1"]["doc_id"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["pinned_doc_id"] == S["main_v1"]["doc_id"]

    db = models.SessionLocal()
    try:
        row = (
            db.query(models.AuditLog)
            .filter(
                models.AuditLog.action == "REPORT_PIN",
                models.AuditLog.target_id == S["main_report"],
            )
            .order_by(models.AuditLog.created_at.desc())
            .first()
        )
        assert row is not None
        assert row.new_value == "v1 고정"
    finally:
        db.close()


def test_pin_other_reports_doc_422(client, staff_headers):
    resp = _pin(client, staff_headers, S["main_report"], S["other_v1"]["doc_id"])
    assert resp.status_code == 422
    assert "이 보고서에 업로드된 문서만" in resp.json()["detail"]

    # 존재하지 않는 문서도 동일 취급
    resp = _pin(client, staff_headers, S["main_report"], "no-such-doc")
    assert resp.status_code == 422


def test_unpin_null_restores_latest(client, staff_headers):
    resp = _pin(client, staff_headers, S["main_report"], None)
    assert resp.status_code == 200, resp.text
    assert resp.json()["pinned_doc_id"] is None

    db = models.SessionLocal()
    try:
        row = (
            db.query(models.AuditLog)
            .filter(
                models.AuditLog.action == "REPORT_PIN",
                models.AuditLog.target_id == S["main_report"],
            )
            .order_by(models.AuditLog.created_at.desc(), models.AuditLog.log_id.desc())
            .all()
        )
        assert row[0].new_value == "고정 해제"
    finally:
        db.close()


def test_send_uses_pinned_doc(client, staff_headers, monkeypatch):
    """핵심 — 고정본(v1) 우선 발송: 첨부 파일명이 v1 (최신 doc_id는 v2인데도)."""
    resp = _pin(client, staff_headers, S["main_report"], S["main_v1"]["doc_id"])
    assert resp.status_code == 200, resp.text

    sent = _send_and_capture(client, staff_headers, S["main_report"], monkeypatch)
    assert len(sent["attachments"]) == 1
    filename = sent["attachments"][0][0]
    assert "report-v1" in filename, filename
    assert "report-v2" not in filename


def test_pin_blocked_after_sent_409(client, staff_headers):
    """SENT(종결 단계) — 고정본 변경 무의미, 409. 해제(null)도 동일."""
    resp = _pin(client, staff_headers, S["main_report"], S["main_v2"]["doc_id"])
    assert resp.status_code == 409
    assert "고정본을 변경할 수 없습니다" in resp.json()["detail"]

    resp = _pin(client, staff_headers, S["main_report"], None)
    assert resp.status_code == 409


def test_pin_blocked_on_canceled_409(client, staff_headers):
    resp = client.put(
        API + "/reports/{0}/status".format(S["other_report"]),
        headers=staff_headers,
        json={"status": "CANCELED", "canceled_reason": "고정본 테스트 취소"},
    )
    assert resp.status_code == 200, resp.text

    resp = _pin(client, staff_headers, S["other_report"], S["other_v1"]["doc_id"])
    assert resp.status_code == 409


def test_send_unpinned_uses_latest(client, staff_headers, monkeypatch):
    """고정 해제 상태(pinned_doc_id=None) — 최신본(doc_id) 발송 확인."""
    report_id = S["lost_report"]
    _upload(client, staff_headers, report_id, "lost-v1.pdf")
    S["lost_v2"] = _upload(client, staff_headers, report_id, "lost-v2.pdf")

    sent = _send_and_capture(client, staff_headers, report_id, monkeypatch)
    assert "lost-v2" in sent["attachments"][0][0]


def test_send_missing_file_409(client, staff_headers, monkeypatch):
    """저장소 파일 소실 — 발송 409 (사전조건 실패, 500 '서버 오류' 오인 방지)."""
    monkeypatch.setenv("GMAIL_SENDER", "hooxi12345@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")

    # 최신본 파일을 디스크에서 제거 (로컬 저장소 — UPLOAD_DIR 상대 경로)
    db = models.SessionLocal()
    try:
        doc = db.get(models.Document, S["lost_v2"]["doc_id"])
        path = os.path.join(os.environ["UPLOAD_DIR"], doc.file_url)
        assert os.path.isfile(path)
        os.remove(path)
    finally:
        db.close()

    resp = client.post(API + "/reports/{0}/send".format(S["lost_report"]), headers=staff_headers)
    assert resp.status_code == 409, resp.text
    assert "저장소에서 읽을 수 없습니다" in resp.json()["detail"]
