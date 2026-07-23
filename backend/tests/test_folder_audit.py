"""Dropbox 폴더 작업 감사 이력 — provision/백필/폴더 소실을 tb_audit_log에 남긴다.

목적: 차후 폴더가 이상하면 "시스템이 언제·누구에 의해·어떤 경로로 만들었는지" + "외부(수동)
삭제로 사라졌는지"를 추적해, 원인이 프로그램인지 외부 개입인지 구분한다(오명 방지).
"""

import models
from routers import batch
from services import client_folders, dropbox_storage

API = "/api/v1"


def _audits(db, action, target_id=None):
    q = db.query(models.AuditLog).filter(models.AuditLog.action == action)
    if target_id:
        q = q.filter(models.AuditLog.target_id == target_id)
    return q.all()


def test_provision_writes_audit(client, monkeypatch):
    monkeypatch.setenv("DROPBOX_APP_KEY", "k")
    monkeypatch.setenv("DROPBOX_APP_SECRET", "s")
    monkeypatch.setenv("DROPBOX_REFRESH_TOKEN", "r")
    monkeypatch.setattr(dropbox_storage, "ensure_folder", lambda p: True)
    db = models.SessionLocal()
    try:
        c = models.Client(client_id="audprv01", client_type="TRANSPORT",
                          company_name="감사프로비전운수", region="서울")
        db.add(c)
        db.commit()
        client_folders.provision(db, c, actor_id="u-admin")
        db.commit()
        rows = _audits(db, "CLIENT_FOLDER_PROVISION", "audprv01")
        assert len(rows) == 1
        assert rows[0].actor_id == "u-admin"
        assert "created" in rows[0].new_value and "서울_감사프로비전운수_운수" in rows[0].new_value
        # 비밀값 미기록(R2-E6) — 경로/액션만
        assert "password" not in (rows[0].new_value or "").lower()
    finally:
        db.close()


def test_provision_without_actor_no_audit(client, monkeypatch):
    monkeypatch.setenv("DROPBOX_APP_KEY", "k")
    monkeypatch.setenv("DROPBOX_APP_SECRET", "s")
    monkeypatch.setenv("DROPBOX_REFRESH_TOKEN", "r")
    monkeypatch.setattr(dropbox_storage, "ensure_folder", lambda p: True)
    db = models.SessionLocal()
    try:
        c = models.Client(client_id="audprv02", client_type="TRANSPORT",
                          company_name="무액터운수", region="서울")
        db.add(c)
        db.commit()
        client_folders.provision(db, c)  # actor 없음 → 감사 미기록
        db.commit()
        assert _audits(db, "CLIENT_FOLDER_PROVISION", "audprv02") == []
    finally:
        db.close()


def test_folder_missing_writes_audit(client, admin_headers, monkeypatch):
    """고객사 폴더 브라우즈가 DropboxNotFound → CLIENT_FOLDER_MISSING 감사(외부 삭제 근거)."""
    monkeypatch.setenv("DROPBOX_APP_KEY", "k")
    monkeypatch.setenv("DROPBOX_APP_SECRET", "s")
    monkeypatch.setenv("DROPBOX_REFRESH_TOKEN", "r")
    db = models.SessionLocal()
    try:
        db.add(models.Client(client_id="audmiss1", client_type="TRANSPORT",
                            company_name="소실운수", dropbox_folder="/Hooxi-CMS/서울_소실운수_운수"))
        db.commit()
    finally:
        db.close()

    def _nf(p):
        raise dropbox_storage.DropboxNotFound(p)

    monkeypatch.setattr(dropbox_storage, "list_folder", _nf)
    r = client.get(API + "/clients/audmiss1/dropbox/tree", headers=admin_headers)
    assert r.status_code == 404

    db = models.SessionLocal()
    try:
        rows = _audits(db, "CLIENT_FOLDER_MISSING", "audmiss1")
        assert len(rows) == 1
        assert rows[0].new_value == "/Hooxi-CMS/서울_소실운수_운수"
    finally:
        db.close()


def test_backfill_writes_summary_and_per_client_audit(client, admin_headers, monkeypatch):
    monkeypatch.setenv("DROPBOX_APP_KEY", "k")
    monkeypatch.setenv("DROPBOX_APP_SECRET", "s")
    monkeypatch.setenv("DROPBOX_REFRESH_TOKEN", "r")
    monkeypatch.setattr(dropbox_storage, "ensure_folder", lambda p: True)
    db = models.SessionLocal()
    try:
        db.add(models.Client(client_id="audbf001", client_type="TRANSPORT",
                            company_name="백필감사운수", region="서울"))
        db.commit()
    finally:
        db.close()

    r = client.post(API + "/batch/provision-dropbox-folders", headers=admin_headers)
    assert r.status_code == 200, r.text

    db = models.SessionLocal()
    try:
        assert len(_audits(db, "CLIENT_FOLDER_PROVISION", "audbf001")) == 1
        assert len(_audits(db, "DROPBOX_BACKFILL")) >= 1  # 요약 감사
    finally:
        db.close()
