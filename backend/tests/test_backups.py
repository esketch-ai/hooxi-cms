"""백업·복구 API — RBAC·미설정 게이트·복구 확인 문구·감사 로그 (Cloud SQL 모킹)."""

import models
from services import gcp_sql


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


def test_backups_admin_only(client, staff_headers):
    assert client.get("/api/v1/backups", headers=staff_headers).status_code == 403
    assert client.get("/api/v1/backups").status_code == 401


def test_backups_unconfigured_503(client, admin_headers):
    """GCP_PROJECT/CLOUDSQL_INSTANCE 미설정(로컬) — 503 한국어 게이트."""
    resp = client.get("/api/v1/backups", headers=admin_headers)
    assert resp.status_code == 503
    assert "설정되지 않았습니다" in resp.json()["detail"]


def test_backup_list_and_create(client, admin_headers, monkeypatch):
    monkeypatch.setattr(
        gcp_sql,
        "list_backup_runs",
        lambda max_results=30: [
            {
                "id": "1111",
                "type": "AUTOMATED",
                "status": "SUCCESSFUL",
                "startTime": "2026-07-09T20:00:00Z",
                "endTime": "2026-07-09T20:03:00Z",
            }
        ],
    )
    resp = client.get("/api/v1/backups", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["policy"]["retention_days"] == 15
    assert body["items"][0]["backup_run_id"] == "1111"

    monkeypatch.setattr(
        gcp_sql, "create_backup", lambda description="": {"name": "op-1", "status": "PENDING"}
    )
    resp = client.post("/api/v1/backups", headers=admin_headers)
    assert resp.status_code == 202
    assert resp.json()["operation_id"] == "op-1"
    assert _audits("BACKUP_CREATE")


def test_restore_requires_confirm_word(client, admin_headers, monkeypatch):
    monkeypatch.setattr(
        gcp_sql, "restore_backup", lambda run_id: {"name": "op-2", "status": "RUNNING"}
    )
    # 확인 문구 불일치 → 422, 복구 호출·감사 기록 없음
    resp = client.post(
        "/api/v1/backups/1111/restore",
        json={"confirm": "restore"},
        headers=admin_headers,
    )
    assert resp.status_code == 422
    assert not _audits("BACKUP_RESTORE")

    resp = client.post(
        "/api/v1/backups/1111/restore",
        json={"confirm": "복구", "backup_date": "2026-07-09 05:00"},
        headers=admin_headers,
    )
    assert resp.status_code == 202
    logs = _audits("BACKUP_RESTORE")
    assert logs and logs[0].target_id == "1111"
    assert logs[0].new_value == "2026-07-09 05:00"


def test_operation_status(client, admin_headers, monkeypatch):
    monkeypatch.setattr(
        gcp_sql,
        "get_operation",
        lambda op_id: {"name": op_id, "status": "DONE"},
    )
    resp = client.get("/api/v1/backups/operations/op-2", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "DONE"
