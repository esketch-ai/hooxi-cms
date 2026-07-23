"""고객사 Dropbox 전용 폴더 provision — 회사명_짧은ID 루트 + 구분 서브폴더.

- 서브폴더 세트: tb_code 카테고리 CLIENT_FOLDER의 active 코드 label(정렬순). 하드코딩 없음.
- 폴더명: {sanitize(company_name) or 'client'}_{client_id[:4]} — 단일 세그먼트(슬래시 제거).
- provision: Dropbox 미설정이면 스킵. 설정 시 루트+서브폴더를 ensure_folder(멱등)로 생성하고
  client.dropbox_folder에 루트 경로를 저장(커밋은 호출부 책임). 회사명 개명 시에도 폴더는
  dropbox_folder에 고정돼 유지되며, 재실행은 ensure_folder 멱등성으로 누락분을 복구한다.
"""

import json

from models import Client, Code, Config
from services import dropbox_storage, storage

CATEGORY = "CLIENT_FOLDER"

# 폴더 분류 토큰 — client_type 코드 → 폴더용 짧은 분류(공통코드 '라벨'과는 별개).
# tb_config client_type_folder_tokens(JSON {code: token})로 override/추가 가능.
_FOLDER_TOKEN_CONFIG_KEY = "client_type_folder_tokens"
_DEFAULT_FOLDER_TOKENS = {
    "TRANSPORT": "운수",
    "BUILDING": "빌딩",
    "FACTORY": "공장",
    "FARM": "농장",
    "FACILITY": "시설",
    "ETC": "기타",
}


def subfolder_labels(db):
    """구분 서브폴더 라벨 목록 — tb_code CLIENT_FOLDER active, sort_order 순."""
    rows = (
        db.query(Code)
        .filter(Code.category == CATEGORY, Code.active == "Y")
        .order_by(Code.sort_order)
        .all()
    )
    return [r.label for r in rows]


def subfolder_label_for_code(db, code):
    """CLIENT_FOLDER 코드 → 현재 라벨(=실제 폴더명). 없으면 None.

    업로드 라우팅이 provision된 서브폴더와 동일 위치를 쓰도록, 안정 키(code)로 조회해
    라벨(폴더명)을 해석한다(라벨이 개명돼도 코드는 불변).
    """
    row = (
        db.query(Code)
        .filter(Code.category == CATEGORY, Code.code == code)
        .first()
    )
    return row.label if row else None


def resolve_recipient_file(db, client, folder_code, name_contains=None):
    """mail-merge용 — 고객사 자신의 {folder_code} 구분폴더에서 첨부할 파일 1개 해석.

    선택 규칙: (선택) name_contains 부분일치 필터 → server_modified 최신 1개.
    반환: (Dropbox 절대경로, size바이트) 튜플. 아래는 None(호출부가 FAIL 격리):
    - 고객사 미provision(dropbox_folder 없음)
    - 코드→라벨 해석 실패 / 폴더 미생성(DropboxNotFound) / Dropbox 미설정(DropboxConfigError)
    - 조건에 맞는 파일 없음
    provision과 동일 sanitize(폴더명) + confinement 재검증으로 경로 일치·탈출 방지.
    size를 함께 반환해 호출부의 별도 file_size 재조회(메타 API 왕복)를 없앤다.
    """
    if not getattr(client, "dropbox_folder", None):
        return None
    label = subfolder_label_for_code(db, folder_code)
    if not label:
        return None
    safe = storage.sanitize_segment(label)
    folder_path = normalize_dropbox_path("{0}/{1}".format(client.dropbox_folder, safe))
    if not is_within_client_folder(client, folder_path):  # 방어적 재검증
        return None
    try:
        entries = dropbox_storage.list_folder(folder_path)
    except (dropbox_storage.DropboxNotFound, dropbox_storage.DropboxConfigError):
        return None
    files = [e for e in entries if not e["is_dir"]]
    if name_contains:
        files = [e for e in files if name_contains in e["name"]]
    if not files:
        return None
    files.sort(key=lambda e: e.get("modified") or "", reverse=True)  # 최신 1개
    return files[0]["path_display"], files[0].get("size")


def normalize_dropbox_path(path):
    """Dropbox 경로 정규화 — 앞 '/' 보장, 빈·'.'·'..' 세그먼트 제거(상위 탈출 방지)."""
    segs = [s for s in (path or "").split("/") if s and s not in (".", "..")]
    return "/" + "/".join(segs)


def is_within_folder(base, path):
    """path가 base(정규화) 하위(자신 포함)인지. base가 비면 False.

    접두사 유사경로 오탐 방지를 위해 경계는 base 자신 또는 'base/' 접두로만 인정한다.
    (고객사 폴더·공용 폴더 등 임의 base에 재사용하는 단일 소스.)
    """
    if not base:
        return False
    base = normalize_dropbox_path(base)
    p = normalize_dropbox_path(path)
    return p == base or p.startswith(base + "/")


def is_within_client_folder(client, path):
    """path가 해당 고객사 dropbox_folder 하위인지 — 미provision이면 False."""
    return is_within_folder(getattr(client, "dropbox_folder", None), path)


def public_send_root():
    """세그먼트 공용 발송자료 폴더(root 기준). 예: root()='' → '/공용_발송자료'."""
    return normalize_dropbox_path("{0}/공용_발송자료".format(dropbox_storage.root()))


def folder_tokens(db):
    """client_type 코드 → 폴더 분류 토큰. tb_config 우선, 기본값 병합."""
    tokens = dict(_DEFAULT_FOLDER_TOKENS)
    row = db.get(Config, _FOLDER_TOKEN_CONFIG_KEY)
    if row and row.config_value:
        try:
            parsed = json.loads(row.config_value)
            if isinstance(parsed, dict):
                tokens.update({str(k): str(v) for k, v in parsed.items() if v})
        except ValueError:
            pass
    return tokens


def _region_seg(client):
    """지역 세그먼트 — sanitize(region), 미입력이면 '지역미상'."""
    return storage.sanitize_segment((getattr(client, "region", None) or "").strip()) or "지역미상"


def _type_seg(client, tokens):
    """분류 토큰 세그먼트 — client_type 매핑 토큰, 없으면 코드값(그것도 없으면 '기타')."""
    tok = tokens.get(client.client_type or "")
    return storage.sanitize_segment(tok or client.client_type or "") or "기타"


def folder_name(db, client):
    """폴더명 = {지역}_{회사명}_{분류토큰}. (실무 규약: 지역+고객사명+분류)

    유일성은 짧은ID 대신 provision 단계의 충돌 접미사(_2, _3 …)로 보장 — 정상 케이스는
    깨끗한 이름 그대로, 동명·동지역·동분류 충돌 시에만 접미사가 붙어 파일 혼입을 막는다.
    """
    raw = (client.company_name or "").replace("/", " ")
    name = storage.sanitize_segment(raw) or "client"
    return "{0}_{1}_{2}".format(_region_seg(client), name, _type_seg(client, folder_tokens(db)))


def upload_base(db, client):
    """업로드 저장 base 세그먼트(root 제외).

    provision된 폴더명(dropbox_folder의 마지막 세그먼트)을 우선 사용해, 회사명 개명·규칙
    변경 후에도 업로드가 provision 폴더로 고정된다. 미provision(None)이면 현재 규칙으로 계산.
    고객사 미지정(공용 양식 등)은 _공용.
    """
    if client is None:
        return "_공용"
    if getattr(client, "dropbox_folder", None):
        return client.dropbox_folder.rstrip("/").split("/")[-1]
    return folder_name(db, client)


def _folder_taken_by_other(db, client, root):
    """다른 고객사가 이미 이 dropbox_folder 경로를 점유 중인지 — 충돌(파일 혼입) 방지."""
    return (
        db.query(Client)
        .filter(Client.dropbox_folder == root, Client.client_id != client.client_id)
        .first()
        is not None
    )


def provision(db, client):
    """고객사 Dropbox 폴더 provision(멱등). 반환 요약 dict.

    미설정 시 {"skipped": True}. 성공 시 루트 경로를 client.dropbox_folder에 세팅한다
    (commit은 호출부 책임). 부분 실패도 재실행 시 ensure_folder 멱등성으로 복구된다.
    충돌(동명·동지역·동분류)이면 _2, _3 … 접미사로 고유 경로를 확보해 파일 혼입을 막는다.
    """
    if not dropbox_storage.is_configured():
        return {"skipped": True, "reason": "dropbox_unconfigured"}

    if getattr(client, "dropbox_folder", None):
        # 이미 provision됨 — 저장 경로를 재사용해 누락 서브폴더만 멱등 복구한다.
        # 이름을 재계산하지 않으므로 회사명 개명·규칙 변경 후 재실행해도 폴더 orphan/이중생성이 없다.
        root = client.dropbox_folder
    else:
        # 신규 — 새 규칙으로 계산. 충돌(동명·동지역·동분류) 시 _2, _3 … 접미사로 고유 경로 확보.
        root_base = "{0}/{1}".format(dropbox_storage.root(), folder_name(db, client))
        root = root_base
        suffix = 2
        while _folder_taken_by_other(db, client, root):
            root = "{0}_{1}".format(root_base, suffix)
            suffix += 1
    dropbox_storage.ensure_folder(root)
    subs = subfolder_labels(db)
    for label in subs:
        # 업로드 경로(save_file→sanitize_folder)와 동일한 공용 sanitize로 폴더명을 정하여
        # provision 폴더와 업로드 경로가 항상 일치하게 한다(라벨 개명·특수문자 포함).
        safe = storage.sanitize_segment(label)
        dropbox_storage.ensure_folder("{0}/{1}".format(root, safe))
    client.dropbox_folder = root
    return {"skipped": False, "folder": root, "subfolders": subs}
