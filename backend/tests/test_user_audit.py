"""내부 사용자 감사 이력 + 문서 다운로드 감사 + AuditLogger redact (R2-E6)."""

import models
from services.audit_logger import redact_sensitive_info


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


def test_user_approve_audited(client, admin_headers):
    resp = client.post(
        "/api/v1/auth/email-login", json={"email": "audit-newbie@hooxipartners.com"}
    )
    assert resp.json()["status"] == "PENDING"
    db = models.SessionLocal()
    target = (
        db.query(models.User)
        .filter(models.User.email == "audit-newbie@hooxipartners.com")
        .first()
    )
    db.close()

    resp = client.put(
        "/api/v1/users/{0}/approve".format(target.user_id),
        json={"role": "STAFF"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    logs = _audits("USER_APPROVE")
    assert logs and logs[0].target_id == target.user_id
    assert logs[0].target_type == "USER"
    assert logs[0].old_value == "PENDING"
    assert "STAFF" in logs[0].new_value


def test_user_role_change_and_deactivate_audited(client, admin_headers):
    db = models.SessionLocal()
    target = (
        db.query(models.User)
        .filter(models.User.email == "audit-newbie@hooxipartners.com")
        .first()
    )
    db.close()

    resp = client.put(
        "/api/v1/users/{0}/role".format(target.user_id),
        json={"role": "MANAGER"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    logs = _audits("USER_ROLE_CHANGE")
    assert logs and logs[0].old_value == "STAFF" and logs[0].new_value == "MANAGER"

    resp = client.put(
        "/api/v1/users/{0}/pin-reset".format(target.user_id), headers=admin_headers
    )
    assert resp.status_code == 200
    assert _audits("USER_PIN_RESET")[0].target_id == target.user_id

    resp = client.put(
        "/api/v1/users/{0}/deactivate".format(target.user_id), headers=admin_headers
    )
    assert resp.status_code == 200
    logs = _audits("USER_DEACTIVATE")
    assert logs and logs[0].new_value == "INACTIVE"


def test_document_download_audited(client, admin_headers, tmp_path):
    upload = client.post(
        "/api/v1/documents",
        data={"title": "감사테스트 문서", "doc_type": "ETC"},
        files={"file": ("audit.txt", b"audit-doc", "text/plain")},
        headers=admin_headers,
    )
    assert upload.status_code in (200, 201), upload.text
    doc_id = upload.json()["doc_id"]

    resp = client.get(
        "/api/v1/documents/{0}/download".format(doc_id), headers=admin_headers
    )
    assert resp.status_code == 200
    logs = _audits("DOCUMENT_DOWNLOAD")
    assert logs and logs[0].target_id == doc_id


def test_report_view_action_not_regressed(client):
    """Qwen 회귀 방지: /r/{token} 열람은 REPORT_VIEW/REPORT로 기록되어야 한다.

    (실제 열람 시나리오는 test_kakao_smoke.py::test_view_report_page가 커버 —
    여기서는 헬퍼 자체의 action·target_type 계약을 고정한다.)
    """
    db = models.SessionLocal()
    try:
        from services.audit_logger import AuditLogger

        admin = db.query(models.User).filter(models.User.role == "ADMIN").first()
        log = AuditLogger.report_view(db, admin.user_id, "r-test")
        assert log.action == "REPORT_VIEW" and log.target_type == "REPORT"
        db.rollback()
    finally:
        db.close()


def test_redact_sensitive_values():
    assert redact_sensitive_info("my_password=1234") == "[REDACTED]"
    assert redact_sensitive_info("api_key: abc") == "[REDACTED]"
    assert redact_sensitive_info("BILLED") == "BILLED"
    assert redact_sensitive_info(None) is None
