"""고객사 Dropbox 폴더 provision 서비스 — 이름 규칙·서브폴더·멱등·미설정 폴백."""

import models
from services import client_folders, dropbox_storage

SUBFOLDERS = ["계약서", "정산", "보고서", "자산·인증정보", "수집데이터", "증빙자료"]


class _FakeClient:
    def __init__(self, name, cid, region="서울", client_type="TRANSPORT"):
        self.company_name = name
        self.client_id = cid
        self.region = region
        self.client_type = client_type


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


def test_is_within_folder_generic_boundary():
    base = "/공용_발송자료"
    assert client_folders.is_within_folder(base, base) is True
    assert client_folders.is_within_folder(base, base + "/공지.pdf") is True
    assert client_folders.is_within_folder(base, "/공용_발송자료_evil/x") is False  # 접두사 오탐
    assert client_folders.is_within_folder(base, "/다른/x") is False
    assert client_folders.is_within_folder("", "/x") is False  # base 없음
    assert client_folders.is_within_folder(None, "/x") is False


def test_public_send_root_uses_root(monkeypatch):
    # DROPBOX_ROOT 미설정 → 기본 /Hooxi-CMS 하위
    assert client_folders.public_send_root() == "/Hooxi-CMS/공용_발송자료"
    monkeypatch.setenv("DROPBOX_ROOT", "/")  # 앱폴더 루트 → 접두 없음
    from services.integration_config import _cache

    _cache.clear()
    assert client_folders.public_send_root() == "/공용_발송자료"


# ---------------------------------------------------------------------------
# 폴더 이름 규칙 (지역_회사명_분류토큰, 단일 세그먼트 · 짧은ID 없음)
# ---------------------------------------------------------------------------
def test_folder_name_basic(client):
    db = models.SessionLocal()
    try:
        assert client_folders.folder_name(
            db, _FakeClient("행복운수", "3f9a1234", region="서울", client_type="TRANSPORT")
        ) == "서울_행복운수_운수"
    finally:
        db.close()


def test_folder_name_region_fallback_and_type_token(client):
    db = models.SessionLocal()
    try:
        # 지역 미입력 → '지역미상', 분류 토큰은 client_type 매핑(BUILDING→빌딩)
        assert client_folders.folder_name(
            db, _FakeClient("스카이빌딩", "aaaa1111", region=None, client_type="BUILDING")
        ) == "지역미상_스카이빌딩_빌딩"
    finally:
        db.close()


def test_folder_name_strips_slash_and_specials(client):
    db = models.SessionLocal()
    try:
        # 슬래시는 폴더 깊이를 만들므로 공백으로, 그 외 특수문자는 치환
        assert client_folders.folder_name(
            db, _FakeClient("A/B 상사", "abcd9999", region="경기", client_type="FACTORY")
        ) == "경기_A B 상사_공장"
    finally:
        db.close()


def test_folder_name_empty_name_falls_back(client):
    db = models.SessionLocal()
    try:
        assert client_folders.folder_name(
            db, _FakeClient("", "wxyz1111", region="부산", client_type="TRANSPORT")
        ) == "부산_client_운수"
    finally:
        db.close()


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
            client_id="prov0002abcd", client_type="BUILDING",
            company_name="테스트빌딩", region="서울",
        )
        db.add(c)
        db.commit()
        res = client_folders.provision(db, c)
        assert res["skipped"] is False
        assert c.dropbox_folder == "/Hooxi-CMS/서울_테스트빌딩_빌딩"
        # 루트 먼저, 이어서 6개 서브폴더(코드 정렬순)
        assert created[0] == "/Hooxi-CMS/서울_테스트빌딩_빌딩"
        assert created[1:] == [
            "/Hooxi-CMS/서울_테스트빌딩_빌딩/" + label for label in SUBFOLDERS
        ]
    finally:
        db.close()


def test_provision_collision_appends_suffix(client, monkeypatch):
    """동명·동지역·동분류 충돌 시 _2 접미사로 고유 경로 확보(파일 혼입 방지)."""
    monkeypatch.setenv("DROPBOX_APP_KEY", "k")
    monkeypatch.setenv("DROPBOX_APP_SECRET", "s")
    monkeypatch.setenv("DROPBOX_REFRESH_TOKEN", "r")
    monkeypatch.setattr(dropbox_storage, "ensure_folder", lambda p: True)
    db = models.SessionLocal()
    try:
        a = models.Client(client_id="colaaaa1", client_type="TRANSPORT",
                          company_name="충돌운수", region="서울")
        b = models.Client(client_id="colbbbb2", client_type="TRANSPORT",
                          company_name="충돌운수", region="서울")
        db.add_all([a, b])
        db.commit()
        client_folders.provision(db, a)
        db.commit()
        assert a.dropbox_folder == "/Hooxi-CMS/서울_충돌운수_운수"
        client_folders.provision(db, b)
        db.commit()
        assert b.dropbox_folder == "/Hooxi-CMS/서울_충돌운수_운수_2"  # 충돌 회피 접미사
    finally:
        db.close()


def test_reprovision_keeps_stored_folder(client, monkeypatch):
    """이미 provision된 고객사 재실행 — 저장 경로 재사용(개명·규칙변경에도 rename/orphan 없음)."""
    monkeypatch.setenv("DROPBOX_APP_KEY", "k")
    monkeypatch.setenv("DROPBOX_APP_SECRET", "s")
    monkeypatch.setenv("DROPBOX_REFRESH_TOKEN", "r")
    created = []
    monkeypatch.setattr(dropbox_storage, "ensure_folder", lambda p: created.append(p) or True)
    db = models.SessionLocal()
    try:
        c = models.Client(client_id="reprv001", client_type="TRANSPORT",
                          company_name="구이름운수", region="서울",
                          dropbox_folder="/Hooxi-CMS/옛경로_구이름운수_운수")
        db.add(c)
        db.commit()
        # 회사명이 바뀌어도(개명) 저장된 경로를 그대로 씀 — 새 규칙으로 재계산하지 않음
        c.company_name = "새이름물류"
        res = client_folders.provision(db, c)
        assert res["skipped"] is False
        assert c.dropbox_folder == "/Hooxi-CMS/옛경로_구이름운수_운수"  # 불변
        assert created[0] == "/Hooxi-CMS/옛경로_구이름운수_운수"        # 저장 경로에 서브폴더 복구
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
    # region 미지정 → 지역미상, TRANSPORT → 운수
    assert folder is not None and folder.startswith("/Hooxi-CMS/지역미상_훅운수_운수")
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
# 업로드 라우팅 — documents.storage_folder가 고객사 폴더(지역_회사명_분류)/6구분으로 매핑
# ---------------------------------------------------------------------------
def test_storage_folder_maps_upload_into_client_folder(client):
    from routers.documents import storage_folder

    db = models.SessionLocal()
    try:
        # 미provision(dropbox_folder 없음) → 현재 규칙으로 계산: 지역미상_문서운수_운수
        c = models.Client(
            client_id="sf01aaaa", client_type="TRANSPORT", company_name="문서운수"
        )
        base = "지역미상_문서운수_운수"
        # 계약서·보고서는 동명 매핑, 현장사진→자산·인증정보, 서명/양식/기타→증빙자료
        assert storage_folder(db, c, "CONTRACT") == base + "/계약서"
        assert storage_folder(db, c, "REPORT") == base + "/보고서"
        assert storage_folder(db, c, "PHOTO") == base + "/자산·인증정보"
        assert storage_folder(db, c, "SIGN") == base + "/증빙자료"
        assert storage_folder(db, c, "FORM") == base + "/증빙자료"
        assert storage_folder(db, c, "ETC") == base + "/증빙자료"
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


# ---------------------------------------------------------------------------
# 세그먼트 공용 발송자료 폴더 조회 GET /segments/dropbox/tree
# ---------------------------------------------------------------------------
PUBLIC_ROOT = "/Hooxi-CMS/공용_발송자료"  # 테스트 env: DROPBOX_ROOT 미설정 → 기본 /Hooxi-CMS


def test_public_tree_503_when_unconfigured(client, admin_headers):
    assert not dropbox_storage.is_configured()
    r = client.get(API + "/segments/dropbox/tree", headers=admin_headers)
    assert r.status_code == 503


def test_public_tree_200_lists_root(client, admin_headers, monkeypatch):
    _dbx_env(monkeypatch)
    monkeypatch.setattr(
        dropbox_storage, "list_folder",
        lambda p: [{"name": "공지.pdf", "path_display": p + "/공지.pdf",
                    "path_lower": (p + "/공지.pdf").lower(), "is_dir": False,
                    "size": 5, "modified": None}],
    )
    r = client.get(API + "/segments/dropbox/tree", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == PUBLIC_ROOT
    assert body["entries"][0]["name"] == "공지.pdf"


def test_public_tree_403_outside_public_root(client, admin_headers, monkeypatch):
    _dbx_env(monkeypatch)
    r = client.get(
        API + "/segments/dropbox/tree",
        params={"path": "/트리e2e운수_9z9z/계약서"}, headers=admin_headers,  # 고객사 폴더는 공용 밖
    )
    assert r.status_code == 403


def test_public_tree_autocreates_root_when_missing(client, admin_headers, monkeypatch):
    _dbx_env(monkeypatch)
    created = []

    def _missing(p):
        raise dropbox_storage.DropboxNotFound(p)

    monkeypatch.setattr(dropbox_storage, "list_folder", _missing)
    monkeypatch.setattr(dropbox_storage, "ensure_folder", lambda p: created.append(p) or True)
    r = client.get(API + "/segments/dropbox/tree", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["entries"] == []  # 자동 생성 후 빈 목록
    assert created == [PUBLIC_ROOT]


# ---------------------------------------------------------------------------
# mail-merge: resolve_recipient_file (수신자별 개별 파일 해석)
# ---------------------------------------------------------------------------
class _MergeClient:
    def __init__(self, folder="/행복운수_1a2b"):
        self.dropbox_folder = folder
        self.client_id = "1a2b0000"
        self.company_name = "행복운수"


def _entry(name, path, is_dir=False, modified=None):
    return {"name": name, "path_display": path, "path_lower": path.lower(),
            "is_dir": is_dir, "size": None if is_dir else 1, "modified": modified}


def test_resolve_recipient_file_latest(client, monkeypatch):
    p_expected = "/행복운수_1a2b/보고서"
    monkeypatch.setattr(dropbox_storage, "list_folder", lambda p: [
        _entry("a.pdf", p + "/a.pdf", modified="2026-07-01T00:00:00"),
        _entry("b.pdf", p + "/b.pdf", modified="2026-07-20T00:00:00"),  # 최신
        _entry("sub", p + "/sub", is_dir=True),
    ])
    db = models.SessionLocal()
    try:
        assert client_folders.resolve_recipient_file(db, _MergeClient(), "REPORT") == (p_expected + "/b.pdf", 1)
    finally:
        db.close()


def test_resolve_recipient_file_name_contains(client, monkeypatch):
    monkeypatch.setattr(dropbox_storage, "list_folder", lambda p: [
        _entry("2026-06.pdf", p + "/2026-06.pdf", modified="2026-06-30T00:00:00"),
        _entry("2026-07.pdf", p + "/2026-07.pdf", modified="2026-07-31T00:00:00"),
    ])
    db = models.SessionLocal()
    try:
        got = client_folders.resolve_recipient_file(db, _MergeClient(), "REPORT", name_contains="2026-06")
        assert got[0].endswith("/2026-06.pdf")  # 최신(07)이 아니라 필터 매칭분
    finally:
        db.close()


def test_resolve_recipient_file_preserves_middot_label(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(dropbox_storage, "list_folder",
                        lambda p: seen.update(path=p) or [_entry("x.jpg", p + "/x.jpg", modified="2026-07-01T00:00:00")])
    db = models.SessionLocal()
    try:
        got = client_folders.resolve_recipient_file(db, _MergeClient(), "ASSET_AUTH")  # 라벨 자산·인증정보
        assert seen["path"] == "/행복운수_1a2b/자산·인증정보"  # · 보존(provision과 동일)
        assert got[0] == "/행복운수_1a2b/자산·인증정보/x.jpg"
    finally:
        db.close()


def test_resolve_recipient_file_none_cases(client, monkeypatch):
    db = models.SessionLocal()
    try:
        # 미provision
        assert client_folders.resolve_recipient_file(db, _MergeClient(folder=None), "REPORT") is None
        # 폴더 없음(DropboxNotFound)
        def _nf(p):
            raise dropbox_storage.DropboxNotFound(p)
        monkeypatch.setattr(dropbox_storage, "list_folder", _nf)
        assert client_folders.resolve_recipient_file(db, _MergeClient(), "REPORT") is None
        # 조건 맞는 파일 없음(폴더뿐)
        monkeypatch.setattr(dropbox_storage, "list_folder", lambda p: [_entry("d", p + "/d", is_dir=True)])
        assert client_folders.resolve_recipient_file(db, _MergeClient(), "REPORT") is None
    finally:
        db.close()
