"""고객사 Dropbox 폴더 provision 서비스 — 이름 규칙·서브폴더·멱등·미설정 폴백."""

import models
from services import client_folders, dropbox_storage

SUBFOLDERS = ["계약서", "정산", "보고서", "자산·인증정보", "수집데이터", "증빙자료"]


class _FakeClient:
    def __init__(self, name, cid):
        self.company_name = name
        self.client_id = cid


# ---------------------------------------------------------------------------
# 폴더 이름 규칙 (회사명_짧은ID, 단일 세그먼트)
# ---------------------------------------------------------------------------
def test_folder_name_basic():
    assert client_folders.folder_name(_FakeClient("행복운수", "3f9a1234")) == "행복운수_3f9a"


def test_folder_name_strips_slash_and_specials():
    # 슬래시는 폴더 깊이를 만들므로 제거, 그 외 특수문자는 치환
    assert client_folders.folder_name(_FakeClient("A/B 상사", "abcd9999")) == "A B 상사_abcd"
    assert client_folders.folder_name(_FakeClient("한:빛*운수", "zzzz0000")) == "한_빛_운수_zzzz"


def test_folder_name_empty_name_falls_back():
    assert client_folders.folder_name(_FakeClient("", "wxyz1111")) == "client_wxyz"


# ---------------------------------------------------------------------------
# 서브폴더 라벨 — tb_code CLIENT_FOLDER 연동 (client 픽스처가 시드)
# ---------------------------------------------------------------------------
def test_subfolder_labels_from_codes(client):
    db = models.SessionLocal()
    try:
        assert client_folders.subfolder_labels(db) == SUBFOLDERS
    finally:
        db.close()


# ---------------------------------------------------------------------------
# provision
# ---------------------------------------------------------------------------
def test_provision_skips_when_unconfigured(client):
    assert not dropbox_storage.is_configured()  # conftest는 Dropbox env 없음
    db = models.SessionLocal()
    try:
        c = models.Client(
            client_id="prov0001", client_type="TRANSPORT", company_name="스킵운수"
        )
        db.add(c)
        db.commit()
        res = client_folders.provision(db, c)
        assert res["skipped"] is True
        assert c.dropbox_folder is None
    finally:
        db.close()


def test_provision_creates_root_and_subfolders(client, monkeypatch):
    monkeypatch.setenv("DROPBOX_APP_KEY", "k")
    monkeypatch.setenv("DROPBOX_APP_SECRET", "s")
    monkeypatch.setenv("DROPBOX_REFRESH_TOKEN", "r")
    created = []
    monkeypatch.setattr(
        dropbox_storage, "ensure_folder", lambda p: created.append(p) or True
    )
    db = models.SessionLocal()
    try:
        c = models.Client(
            client_id="prov0002abcd", client_type="FACILITY", company_name="테스트빌딩"
        )
        db.add(c)
        db.commit()
        res = client_folders.provision(db, c)
        assert res["skipped"] is False
        assert c.dropbox_folder == "/Hooxi-CMS/테스트빌딩_prov"
        # 루트 먼저, 이어서 6개 서브폴더(코드 정렬순)
        assert created[0] == "/Hooxi-CMS/테스트빌딩_prov"
        assert created[1:] == [
            "/Hooxi-CMS/테스트빌딩_prov/" + label for label in SUBFOLDERS
        ]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /clients 등록 훅 (best-effort)
# ---------------------------------------------------------------------------
API = "/api/v1"


def _created_client_folder(cid):
    db = models.SessionLocal()
    try:
        return db.get(models.Client, cid).dropbox_folder
    finally:
        db.close()


def test_create_client_provisions_when_configured(client, admin_headers, monkeypatch):
    monkeypatch.setenv("DROPBOX_APP_KEY", "k")
    monkeypatch.setenv("DROPBOX_APP_SECRET", "s")
    monkeypatch.setenv("DROPBOX_REFRESH_TOKEN", "r")
    created = []
    monkeypatch.setattr(
        dropbox_storage, "ensure_folder", lambda p: created.append(p) or True
    )
    resp = client.post(
        API + "/clients",
        json={"client_type": "TRANSPORT", "company_name": "훅운수"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    folder = _created_client_folder(resp.json()["client_id"])
    assert folder is not None and folder.startswith("/Hooxi-CMS/훅운수_")
    assert any(p.endswith("/계약서") for p in created)


def test_create_client_ok_when_unconfigured(client, admin_headers):
    assert not dropbox_storage.is_configured()
    resp = client.post(
        API + "/clients",
        json={"client_type": "TRANSPORT", "company_name": "미설정운수"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert _created_client_folder(resp.json()["client_id"]) is None


def test_create_client_survives_provision_error(client, admin_headers, monkeypatch):
    monkeypatch.setenv("DROPBOX_APP_KEY", "k")
    monkeypatch.setenv("DROPBOX_APP_SECRET", "s")
    monkeypatch.setenv("DROPBOX_REFRESH_TOKEN", "r")

    def boom(path):
        raise RuntimeError("dropbox down")

    monkeypatch.setattr(dropbox_storage, "ensure_folder", boom)
    resp = client.post(
        API + "/clients",
        json={"client_type": "TRANSPORT", "company_name": "오류운수"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text  # 등록은 성공
    assert _created_client_folder(resp.json()["client_id"]) is None  # 폴더 실패 → 롤백


# ---------------------------------------------------------------------------
# 백필 엔드포인트 (POST /batch/provision-dropbox-folders)
# ---------------------------------------------------------------------------
def test_backfill_503_when_unconfigured(client, admin_headers):
    assert not dropbox_storage.is_configured()
    resp = client.post(API + "/batch/provision-dropbox-folders", headers=admin_headers)
    assert resp.status_code == 503


def test_backfill_provisions_missing_and_is_idempotent(client, admin_headers, monkeypatch):
    monkeypatch.setenv("DROPBOX_APP_KEY", "k")
    monkeypatch.setenv("DROPBOX_APP_SECRET", "s")
    monkeypatch.setenv("DROPBOX_REFRESH_TOKEN", "r")
    monkeypatch.setattr(dropbox_storage, "ensure_folder", lambda p: True)
    db = models.SessionLocal()
    try:
        for i in (1, 2):
            db.add(
                models.Client(
                    client_id="bf000{0}".format(i),
                    client_type="TRANSPORT",
                    company_name="백필운수{0}".format(i),
                )
            )
        db.commit()
    finally:
        db.close()
    resp = client.post(API + "/batch/provision-dropbox-folders", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provisioned"] >= 2 and body["failed"] == 0
    assert body["total"] == body["provisioned"]
    # 재실행 — 이미 folder가 있으니 대상 0 (멱등)
    resp2 = client.post(API + "/batch/provision-dropbox-folders", headers=admin_headers)
    assert resp2.json()["total"] == 0


# ---------------------------------------------------------------------------
# 업로드 라우팅 — documents.storage_folder가 고객사 폴더(회사명_짧은ID)/6구분으로 매핑
# ---------------------------------------------------------------------------
def test_storage_folder_maps_upload_into_client_folder(client):
    from routers.documents import storage_folder

    db = models.SessionLocal()
    try:
        c = models.Client(
            client_id="sf01aaaa", client_type="TRANSPORT", company_name="문서운수"
        )
        # 계약서·보고서는 동명 매핑, 현장사진→자산·인증정보, 서명/양식/기타→증빙자료
        assert storage_folder(db, c, "CONTRACT") == "문서운수_sf01/계약서"
        assert storage_folder(db, c, "REPORT") == "문서운수_sf01/보고서"
        assert storage_folder(db, c, "PHOTO") == "문서운수_sf01/자산·인증정보"
        assert storage_folder(db, c, "SIGN") == "문서운수_sf01/증빙자료"
        assert storage_folder(db, c, "FORM") == "문서운수_sf01/증빙자료"
        assert storage_folder(db, c, "ETC") == "문서운수_sf01/증빙자료"
        # 고객사 미지정(공용 양식)
        assert storage_folder(db, None, "PHOTO") == "_공용/자산·인증정보"
    finally:
        db.close()


def test_storage_folder_uses_pinned_folder_after_rename(client):
    """회사명 개명 후에도 업로드는 provision된 폴더(dropbox_folder)로 고정 저장."""
    from routers.documents import storage_folder

    db = models.SessionLocal()
    try:
        c = models.Client(
            client_id="rn01aaaa", client_type="TRANSPORT", company_name="새이름물류"
        )
        c.dropbox_folder = "/옛이름운수_rn01"  # provision 시점(개명 전) 고정
        # 현재 회사명이 아니라 고정 폴더명을 사용해야 함
        assert storage_folder(db, c, "SIGN") == "옛이름운수_rn01/증빙자료"
        assert storage_folder(db, c, "CONTRACT") == "옛이름운수_rn01/계약서"
    finally:
        db.close()
