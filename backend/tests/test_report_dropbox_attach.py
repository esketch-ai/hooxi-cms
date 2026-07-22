"""보고서 발송 시 고객사 Dropbox 파일 추가 첨부 (라이브 브라우즈) — confinement·총량 검증."""

import pytest

import models
from services import dropbox_storage, email_service, report_sender
from services import storage as storage_mod


def _setup(db, cid, folder, period):
    """발송 가능한 최소 구성 — 고객사(dropbox_folder·수신 이메일) + 보고서 문서 + APPROVED delivery."""
    c = models.Client(
        client_id=cid, client_type="TRANSPORT", company_name="발송운수",
        main_contact_email="to@example.com", dropbox_folder=folder,
    )
    db.add(c)
    db.flush()
    doc = models.Document(
        client_id=cid, doc_type="REPORT", title="보고서",
        file_url="{0}/보고서/uuid_r.pdf".format(folder.lstrip("/")), version=1,
        uploaded_by="u-admin",
    )
    db.add(doc)
    db.flush()
    deliv = models.ReportDelivery(
        client_id=cid, report_type="월간 운행 보고서", period=period,
        status="APPROVED", doc_id=doc.doc_id, manager_id="u-manager",
    )
    db.add(deliv)
    db.commit()
    return deliv


def _mock_send(monkeypatch, captured):
    monkeypatch.setenv("GMAIL_SENDER", "hooxi12345@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setattr(email_service, "is_configured", lambda: True)

    def fake_send_mail(to, subject, body, cc=None, attachments=None, reply_to=None, html=False):
        captured["attachments"] = attachments
        return {"sender": "x", "recipients": list(to)}

    monkeypatch.setattr(email_service, "send_mail", fake_send_mail)
    # 본문 doc은 로컬/실제 미존재 → dropbox는 bytes, 그 외는 본문용 bytes 반환하도록 모킹
    monkeypatch.setattr(
        storage_mod, "read_file",
        lambda url: b"DBX-BYTES" if url.startswith("dropbox:") else b"MAIN-DOC",
    )
    # 다운로드 전 총량 사전검사용 메타 size (기본 작은 값)
    monkeypatch.setattr(dropbox_storage, "file_size", lambda path: 100)


def test_send_attaches_dropbox_file_within_folder(client, monkeypatch):
    captured = {}
    _mock_send(monkeypatch, captured)
    db = models.SessionLocal()
    try:
        deliv = _setup(db, "rscin001", "/발송운수_rsc0", "2028-01")
        report_sender.send_report_core(
            db, deliv, "u-admin",
            dropbox_paths=["/발송운수_rsc0/증빙자료/증빙.pdf"],
        )
        assert deliv.status == "SENT"
        atts = captured["attachments"]
        # 본문 doc + Dropbox 파일 1 = 2개
        assert len(atts) == 2
        assert atts[1][0] == "증빙.pdf" and atts[1][1] == b"DBX-BYTES"
    finally:
        db.close()


def test_send_rejects_path_outside_client_folder(client, monkeypatch):
    captured = {}
    _mock_send(monkeypatch, captured)
    db = models.SessionLocal()
    try:
        deliv = _setup(db, "rscout01", "/발송운수_rscb", "2028-02")
        with pytest.raises(report_sender.SendPrecondition) as ei:
            report_sender.send_report_core(
                db, deliv, "u-admin",
                dropbox_paths=["/다른운수_evil/증빙자료/x.pdf"],  # 다른 고객사 폴더
            )
        assert ei.value.code == 403
        assert "attachments" not in captured  # 발송 자체가 일어나지 않음
    finally:
        db.close()


def test_send_rejects_when_total_exceeds_limit(client, monkeypatch):
    captured = {}
    _mock_send(monkeypatch, captured)
    # 개별 파일이 상한을 넘는 size를 반환 → 다운로드 전 413
    monkeypatch.setattr(dropbox_storage, "file_size", lambda path: 30 * 1024 * 1024)
    db = models.SessionLocal()
    try:
        deliv = _setup(db, "rscbig01", "/발송운수_rscg", "2028-04")
        with pytest.raises(report_sender.SendPrecondition) as ei:
            report_sender.send_report_core(
                db, deliv, "u-admin", dropbox_paths=["/발송운수_rscg/증빙자료/대용량.zip"],
            )
        assert ei.value.code == 413
        assert "attachments" not in captured  # 다운로드·발송 전 차단
    finally:
        db.close()


def test_send_without_dropbox_paths_is_unchanged(client, monkeypatch):
    """경로 미지정 시 기존 발송(본문 doc 1개)과 동일 — 회귀 없음."""
    captured = {}
    _mock_send(monkeypatch, captured)
    db = models.SessionLocal()
    try:
        deliv = _setup(db, "rscnone1", "/발송운수_rscn", "2028-03")
        report_sender.send_report_core(db, deliv, "u-admin")  # dropbox_paths 없음
        assert len(captured["attachments"]) == 1
    finally:
        db.close()
