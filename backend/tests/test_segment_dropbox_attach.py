"""세그먼트 발송 — 공용 발송자료 Dropbox 공통 첨부 (confinement·총량)."""

import pytest
from fastapi import HTTPException

import models
from routers import segments
from services import client_folders, dropbox_storage
from services import storage as storage_mod


def _dbx_env(monkeypatch):
    monkeypatch.setenv("DROPBOX_APP_KEY", "k")
    monkeypatch.setenv("DROPBOX_APP_SECRET", "s")
    monkeypatch.setenv("DROPBOX_REFRESH_TOKEN", "r")


def test_load_attachments_public_dropbox_within_root(client, monkeypatch):
    _dbx_env(monkeypatch)
    monkeypatch.setattr(dropbox_storage, "file_size", lambda p: 100)
    monkeypatch.setattr(storage_mod, "read_file", lambda url: b"PUB-BYTES")
    root = client_folders.public_send_root()
    db = models.SessionLocal()
    try:
        atts = segments._load_attachments(db, [], dropbox_paths=[root + "/공지.pdf"])
        assert len(atts) == 1
        assert atts[0][0] == "공지.pdf" and atts[0][1] == b"PUB-BYTES"
    finally:
        db.close()


def test_load_attachments_rejects_outside_public_root(client, monkeypatch):
    _dbx_env(monkeypatch)
    monkeypatch.setattr(dropbox_storage, "file_size", lambda p: 100)
    db = models.SessionLocal()
    try:
        with pytest.raises(HTTPException) as ei:
            # 고객사 폴더(공용 밖) 경로 → 403
            segments._load_attachments(db, [], dropbox_paths=["/어느고객_1a2b/계약서/x.pdf"])
        assert ei.value.status_code == 403
    finally:
        db.close()


def test_load_attachments_503_when_dropbox_unconfigured(client):
    # 프론트 우회/레이스로 미설정 상태에서 dropbox_paths가 들어와도 500이 아니라 503
    assert not dropbox_storage.is_configured()
    db = models.SessionLocal()
    try:
        with pytest.raises(HTTPException) as ei:
            segments._load_attachments(db, [], dropbox_paths=["/공용_발송자료/x.pdf"])
        assert ei.value.status_code == 503
    finally:
        db.close()


def test_load_attachments_total_limit_across_docs_and_dropbox(client, monkeypatch):
    _dbx_env(monkeypatch)
    monkeypatch.setattr(dropbox_storage, "file_size", lambda p: 30 * 1024 * 1024)
    monkeypatch.setattr(storage_mod, "read_file", lambda url: b"x")
    root = client_folders.public_send_root()
    db = models.SessionLocal()
    try:
        with pytest.raises(HTTPException) as ei:
            segments._load_attachments(db, [], dropbox_paths=[root + "/대용량.zip"])
        assert ei.value.status_code == 422  # 총량 20MB 초과 사전 차단
    finally:
        db.close()
