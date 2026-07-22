"""고객사 Dropbox 전용 폴더 provision — 회사명_짧은ID 루트 + 구분 서브폴더.

- 서브폴더 세트: tb_code 카테고리 CLIENT_FOLDER의 active 코드 label(정렬순). 하드코딩 없음.
- 폴더명: {sanitize(company_name) or 'client'}_{client_id[:4]} — 단일 세그먼트(슬래시 제거).
- provision: Dropbox 미설정이면 스킵. 설정 시 루트+서브폴더를 ensure_folder(멱등)로 생성하고
  client.dropbox_folder에 루트 경로를 저장(커밋은 호출부 책임). 회사명 개명 시에도 폴더는
  dropbox_folder에 고정돼 유지되며, 재실행은 ensure_folder 멱등성으로 누락분을 복구한다.
"""

from models import Code
from services import dropbox_storage, storage

CATEGORY = "CLIENT_FOLDER"


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


def normalize_dropbox_path(path):
    """Dropbox 경로 정규화 — 앞 '/' 보장, 빈·'.'·'..' 세그먼트 제거(상위 탈출 방지)."""
    segs = [s for s in (path or "").split("/") if s and s not in (".", "..")]
    return "/" + "/".join(segs)


def is_within_client_folder(client, path):
    """path가 해당 고객사 dropbox_folder(정규화) 하위(자신 포함)인지.

    미provision(dropbox_folder=None)이면 무조건 False. 접두사 유사경로 오탐 방지를 위해
    경계는 folder 자신 또는 'folder/' 접두로만 인정한다.
    """
    folder = getattr(client, "dropbox_folder", None)
    if not folder:
        return False
    folder = normalize_dropbox_path(folder)
    p = normalize_dropbox_path(path)
    return p == folder or p.startswith(folder + "/")


def _short_id(client_id):
    return (client_id or "")[:4] or "0000"


def folder_name(client):
    """단일 세그먼트 폴더명 — 슬래시는 공백으로, 그 외는 공용 sanitize + 짧은ID(client_id[:4])."""
    raw = (client.company_name or "").replace("/", " ")
    seg = storage.sanitize_segment(raw)
    return "{0}_{1}".format(seg or "client", _short_id(client.client_id))


def upload_base(client):
    """업로드 저장 base 세그먼트(root 제외).

    provision된 폴더명(dropbox_folder의 마지막 세그먼트)을 우선 사용해, 회사명 개명 후에도
    업로드가 provision 폴더로 고정된다. 미provision(None)이면 현재 회사명으로 계산.
    고객사 미지정(공용 양식 등)은 _공용.
    """
    if client is None:
        return "_공용"
    if getattr(client, "dropbox_folder", None):
        return client.dropbox_folder.rstrip("/").split("/")[-1]
    return folder_name(client)


def provision(db, client):
    """고객사 Dropbox 폴더 provision(멱등). 반환 요약 dict.

    미설정 시 {"skipped": True}. 성공 시 루트 경로를 client.dropbox_folder에 세팅한다
    (commit은 호출부 책임). 부분 실패도 재실행 시 ensure_folder 멱등성으로 복구된다.
    """
    if not dropbox_storage.is_configured():
        return {"skipped": True, "reason": "dropbox_unconfigured"}

    root = "{0}/{1}".format(dropbox_storage.root(), folder_name(client))
    dropbox_storage.ensure_folder(root)
    subs = subfolder_labels(db)
    for label in subs:
        # 업로드 경로(save_file→sanitize_folder)와 동일한 공용 sanitize로 폴더명을 정하여
        # provision 폴더와 업로드 경로가 항상 일치하게 한다(라벨 개명·특수문자 포함).
        safe = storage.sanitize_segment(label)
        dropbox_storage.ensure_folder("{0}/{1}".format(root, safe))
    client.dropbox_folder = root
    return {"skipped": False, "folder": root, "subfolders": subs}
