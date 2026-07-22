"""고객사 Dropbox 폴더 provision 서비스 — 이름 규칙·서브폴더·멱등·미설정 폴백."""

import models
from services import client_folders, dropbox_storage

SUBFOLDERS = ["계약서", "정산", "보고서", "자산·인증정보", "수집데이터", "증빙자료"]


class _FakeClient:
    def __init__(self, name, cid):
        self.company_name = name
        self.client_id = cid


# ---------------------------------------------------------------------------
# 경로 confinement (다른 고객사·상위 탈출·접두사 오탐 차단)
# ---------------------------------------------------------------------------
class _PinnedClient:
    dropbox_folder = "/행복운수_1a2b"


def test_confinement_allows_own_subtree():
    c = _PinnedClient()
    assert client_folders.is_within_client_folder(c, "/행복운수_1a2b") is True
    assert client_folders.is_within_client_folder(c, "/행복운수_1a2b/계약서") is True
    assert client_folders.is_within_client_folder(c, "/행복운수_1a2b/계약서/x.pdf") is True


def test_confinement_blocks_escape_and_prefix():
    c = _PinnedClient()
    # 다른 고객사
    assert client_folders.is_within_client_folder(c, "/다른운수_9z9z/계약서") is False
    # 접두사 유사경로 (경계 오탐)
    assert client_folders.is_within_client_folder(c, "/행복운수_1a2b_evil/x") is False
    # 앱 루트
    assert client_folders.is_within_client_folder(c, "/") is False


def test_normalize_neutralizes_traversal():
    # '..'는 제거되어 상위로 이동 불가 → 경로가 하위로 접힘(sibling 탈출 불가)
    assert client_folders.normalize_dropbox_path("/a/../b") == "/a/b"
    assert client_folders.normalize_dropbox_path("//a///b/") == "/a/b"
    # '..'로 sibling 탈출을 시도해도 정규화 후 고객사 폴더 하위에 머문다(실폴더 없으면 조회 시 404)
    c = _PinnedClient()
    p = client_folders.normalize_dropbox_path("/행복운수_1a2b/../다른운수_9z9z")
    assert p == "/행복운수_1a2b/다른운수_9z9z"  # 실제 /다른운수_9z9z 에 도달하지 못함
    assert client_folders.is_within_client_folder(c, p) is True


def test_confinement_false_when_unprovisioned():
    class NoFolder:
        dropbox_folder = None

    assert client_folders.is_within_client_folder(NoFolder(), "/무엇이든/x") is False


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


# ---------------------------------------------------------------------------
# 조회 엔드포인트 GET /clients/{id}/dropbox/tree (라이브 브라우즈)
# ---------------------------------------------------------------------------
def _dbx_env(monkeypatch):
    monkeypatch.setenv("DROPBOX_APP_KEY", "k")
    monkeypatch.setenv("DROPBOX_APP_SECRET", "s")
    monkeypatch.setenv("DROPBOX_REFRESH_TOKEN", "r")


def _mk_client(cid, name, folder):
    db = models.SessionLocal()
    try:
        db.add(
            models.Client(
                client_id=cid, client_type="TRANSPORT", company_name=name,
                dropbox_folder=folder,
            )
        )
        db.commit()
    finally:
        db.close()


def test_tree_409_when_unprovisioned(client, admin_headers):
    _mk_client("tree409aa", "트리미설정", None)
    r = client.get(API + "/clients/tree409aa/dropbox/tree", headers=admin_headers)
    assert r.status_code == 409


def test_tree_503_when_dropbox_unconfigured(client, admin_headers):
    _mk_client("tree503aa", "트리503", "/트리503_tree")
    assert not dropbox_storage.is_configured()
    r = client.get(API + "/clients/tree503aa/dropbox/tree", headers=admin_headers)
    assert r.status_code == 503


def test_tree_200_lists_entries(client, admin_headers, monkeypatch):
    _mk_client("tree200aa", "트리200", "/트리200_tree")
    _dbx_env(monkeypatch)
    monkeypatch.setattr(
        dropbox_storage, "list_folder",
        lambda p: [
            {"name": "계약서", "path_display": p + "/계약서", "path_lower": (p + "/계약서").lower(),
             "is_dir": True, "size": None, "modified": None},
            {"name": "a.pdf", "path_display": p + "/a.pdf", "path_lower": (p + "/a.pdf").lower(),
             "is_dir": False, "size": 10, "modified": "2026-07-22T00:00:00"},
        ],
    )
    r = client.get(API + "/clients/tree200aa/dropbox/tree", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "/트리200_tree"
    assert [e["name"] for e in body["entries"]] == ["계약서", "a.pdf"]
    assert body["entries"][1]["size"] == 10


def test_tree_403_confinement(client, admin_headers, monkeypatch):
    _mk_client("tree403aa", "트리403", "/트리403_tree")
    _dbx_env(monkeypatch)
    r = client.get(
        API + "/clients/tree403aa/dropbox/tree",
        params={"path": "/다른고객_evil/계약서"}, headers=admin_headers,
    )
    assert r.status_code == 403


def test_tree_404_when_not_found(client, admin_headers, monkeypatch):
    _mk_client("tree404aa", "트리404", "/트리404_tree")
    _dbx_env(monkeypatch)

    def _raise_not_found(p):
        raise dropbox_storage.DropboxNotFound(p)

    monkeypatch.setattr(dropbox_storage, "list_folder", _raise_not_found)
    r = client.get(
        API + "/clients/tree404aa/dropbox/tree",
        params={"path": "/트리404_tree/없는폴더"}, headers=admin_headers,
    )
    assert r.status_code == 404
