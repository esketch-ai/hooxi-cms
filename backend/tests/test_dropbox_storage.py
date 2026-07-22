"""Dropbox 저장소 — 스킴 라우팅·업체별 폴더 규칙·미설정 폴백 (SDK 모킹)."""

import io

from sqlalchemy import func as sa_func

import models
from services import dropbox_storage, storage


# ---------------------------------------------------------------------------
# 폴더 규칙 (storage_folder 매핑 테스트는 test_client_folders.py로 이동 —
#  이제 고객사 폴더/6구분 기준이라 tb_code·client가 필요)
# ---------------------------------------------------------------------------
def test_sanitize_folder_segments():
    # 세그먼트별 안전화 — 슬래시로 폴더 깊이 유지, 특수문자 치환, 한글·공백 유지
    assert storage.sanitize_folder("한빛운수/현장사진") == "한빛운수/현장사진"
    assert storage.sanitize_folder("A:B*상사/기타") == "A_B_상사/기타"
    assert storage.sanitize_folder("  테스트 상사 /계약서") == "테스트 상사/계약서"


# ---------------------------------------------------------------------------
# 스킴 라우팅 (미설정 → 로컬 폴백 회귀)
# ---------------------------------------------------------------------------
def test_save_falls_back_to_local_when_unconfigured():
    assert not dropbox_storage.is_configured()  # conftest는 Dropbox env 없음
    url = storage.save_file(b"bytes", "폴백.txt", folder="한빛운수/기타")
    assert not url.startswith("dropbox:") and not url.startswith("gs://")
    assert url.startswith("한빛운수/기타/")
    assert storage.read_file(url) == b"bytes"
    assert storage.delete_file(url) is True


# ---------------------------------------------------------------------------
# Dropbox 설정 시 동작 (모킹)
# ---------------------------------------------------------------------------
def _configure(monkeypatch):
    monkeypatch.setenv("DROPBOX_APP_KEY", "k")
    monkeypatch.setenv("DROPBOX_APP_SECRET", "s")
    monkeypatch.setenv("DROPBOX_REFRESH_TOKEN", "r")


# ---------------------------------------------------------------------------
# ensure_folder — 빈 폴더 생성(멱등)
# ---------------------------------------------------------------------------
def test_ensure_folder_creates(monkeypatch):
    _configure(monkeypatch)
    calls = []

    class FakeDbx:
        def files_create_folder_v2(self, path):
            calls.append(path)
            return object()

    monkeypatch.setattr(dropbox_storage, "_get_client", lambda: FakeDbx())
    assert dropbox_storage.ensure_folder("/Hooxi-CMS/행복운수_3f9a/계약서") is True
    assert calls == ["/Hooxi-CMS/행복운수_3f9a/계약서"]


def test_ensure_folder_idempotent_on_conflict(monkeypatch):
    _configure(monkeypatch)
    import dropbox

    conflict = dropbox.exceptions.ApiError(
        "req",
        dropbox.files.CreateFolderError.path(
            dropbox.files.WriteError.conflict(dropbox.files.WriteConflictError.folder)
        ),
        "already exists",
        None,
    )

    class FakeDbx:
        def files_create_folder_v2(self, path):
            raise conflict

    monkeypatch.setattr(dropbox_storage, "_get_client", lambda: FakeDbx())
    # 이미 존재하는 폴더 → conflict를 성공으로 흡수(멱등)
    assert dropbox_storage.ensure_folder("/Hooxi-CMS/중복") is True


def test_ensure_folder_raises_when_unconfigured():
    import pytest

    assert not dropbox_storage.is_configured()  # conftest는 Dropbox env 없음
    with pytest.raises(dropbox_storage.DropboxConfigError):
        dropbox_storage.ensure_folder("/Hooxi-CMS/x")


def test_save_uses_dropbox_scheme_and_path(monkeypatch):
    _configure(monkeypatch)
    captured = {}

    def fake_upload(content, path):
        captured["path"] = path
        return path  # path_display 그대로

    monkeypatch.setattr(dropbox_storage, "upload", fake_upload)
    url = storage.save_file(b"img", "현장 사진(1).jpg", folder="한빛운수/현장사진")
    assert url.startswith("dropbox:/Hooxi-CMS/한빛운수/현장사진/")
    assert captured["path"].startswith("/Hooxi-CMS/한빛운수/현장사진/")
    assert captured["path"].endswith("_현장_사진_1_.jpg")  # 파일명 sanitize


def test_get_url_and_read_route_to_dropbox(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(
        dropbox_storage, "temporary_link", lambda p: "https://dl.dropboxusercontent.com/x"
    )
    monkeypatch.setattr(dropbox_storage, "download", lambda p: b"content")
    url = "dropbox:/Hooxi-CMS/한빛운수/보고서/2026-07/ab_x.pdf"
    assert storage.get_url(url) == "https://dl.dropboxusercontent.com/x"
    assert storage.read_file(url) == b"content"


def test_document_upload_uses_company_folder(client, admin_headers, monkeypatch):
    """업로드 API가 업체별 폴더 규칙으로 저장하는지 (Dropbox 설정 상태 모킹)."""
    _configure(monkeypatch)
    captured = {}

    def fake_upload(content, path):
        captured["path"] = path
        return path

    monkeypatch.setattr(dropbox_storage, "upload", fake_upload)
    # 등록 훅(provision)이 실 네트워크를 타지 않도록 폴더 생성도 모킹
    monkeypatch.setattr(dropbox_storage, "ensure_folder", lambda p: True)

    resp = client.post(
        "/api/v1/clients",
        json={"client_type": "TRANSPORT", "company_name": "QA-드롭박스운수"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    cid = resp.json()["client_id"]

    resp = client.post(
        "/api/v1/documents",
        data={"title": "QA-드롭박스 사진", "doc_type": "PHOTO", "client_id": cid},
        files={"file": ("현장.jpg", io.BytesIO(b"jpg"), "image/jpeg")},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    # PHOTO → 고객사 폴더(회사명_짧은ID)/자산·인증정보 (provision과 동일 위치)
    assert captured["path"].startswith(
        "/Hooxi-CMS/QA-드롭박스운수_{0}/자산·인증정보/".format(cid[:4])
    )
    assert resp.json()["file_url"].startswith("dropbox:/Hooxi-CMS/")


def test_view_page_uses_external_link_for_dropbox(client, admin_headers, monkeypatch):
    """/r/{token} 열람 페이지가 dropbox 파일에 임시 링크를 쓰는지."""
    import jwt as pyjwt
    from datetime import datetime, timedelta, timezone

    _configure(monkeypatch)
    monkeypatch.setattr(
        dropbox_storage, "temporary_link", lambda p: "https://dl.dropboxusercontent.com/tmp"
    )

    db = models.SessionLocal()
    delivery = db.query(models.ReportDelivery).first()
    if delivery is None:
        cid = (
            db.query(models.Client.client_id).first() or [None]
        )[0]
        delivery = models.ReportDelivery(
            client_id=cid, period="2026-07", report_type="월간", status="SENT"
        )
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
    # (report_id, version) 유니크 인덱스(P0-B) — 기존 문서가 있는 보고서라도
    # 충돌하지 않도록 다음 버전을 계산해 시드
    next_version = (
        db.query(sa_func.max(models.Document.version))
        .filter(models.Document.report_id == delivery.report_id)
        .scalar()
        or 0
    ) + 1
    doc = models.Document(
        client_id=delivery.client_id,
        doc_type="REPORT",
        title="드롭박스 열람 테스트",
        file_url="dropbox:/Hooxi-CMS/한빛운수/보고서/2026-07/x.pdf",
        version=next_version,
        report_id=delivery.report_id,
        uploaded_by="u-admin",
    )
    db.add(doc)
    db.commit()
    token = pyjwt.encode(
        {
            "type": "view",
            "doc_id": doc.doc_id,
            "report_id": delivery.report_id,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "test",
        algorithm="HS256",
    )
    db.close()

    resp = client.get("/r/{0}".format(token))
    assert resp.status_code == 200
    assert "https://dl.dropboxusercontent.com/tmp" in resp.text
