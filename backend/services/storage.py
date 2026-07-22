"""파일 저장소 — 스킴 라우터.

저장 우선순위(신규 업로드): Dropbox(설정 시) > GCS(GCS_BUCKET) > 로컬 uploads/.
읽기·URL·삭제는 file_url 스킴으로 라우팅해 3종이 공존한다(하위 호환):
  - "dropbox:/Hooxi-CMS/..."  → Dropbox (services/dropbox_storage.py)
  - "gs://{bucket}/{object}"  → Google Cloud Storage
  - 그 외(상대 경로)           → 로컬 UPLOAD_DIR

DB(tb_document.file_url)에는 본 모듈이 반환하는 경로/URL만 저장한다 (Server.pdf §3).
google-cloud-storage·dropbox는 선택적 import — 미설치 환경에서도 앱이 뜬다.
"""

import os
import re
import uuid
from typing import Optional

from services import dropbox_storage

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))

GCS_BUCKET = os.getenv("GCS_BUCKET")

DROPBOX_SCHEME = "dropbox:"


class StorageError(RuntimeError):
    pass


def _sanitize_filename(filename: str) -> str:
    name = os.path.basename(filename or "file")
    return re.sub(r"[^\w.\-가-힣]", "_", name)


def sanitize_segment(name: str) -> str:
    """단일 경로 세그먼트 안전화 — 폴더명·라벨 공용 단일 소스.

    슬래시 등 허용 외 문자는 _로 치환(단일 세그먼트 보장). 가운뎃점(·)은 공통코드
    라벨(예: 자산·인증정보)에 쓰이므로 보존 — provision 폴더명과 업로드 경로 일치 유지.
    """
    return re.sub(r"[^\w.\-가-힣· ]", "_", name or "").strip()


def sanitize_folder(folder: str) -> str:
    """폴더 경로 세그먼트별 sanitize — 슬래시로 깊이 유지, 세그먼트는 sanitize_segment."""
    parts = [p for p in (folder or "").split("/") if p.strip()]
    return "/".join(sanitize_segment(p) for p in parts)


def _object_name(filename: str, folder: str) -> str:
    safe = _sanitize_filename(filename)
    folder = sanitize_folder(folder)
    return f"{folder}/{uuid.uuid4().hex[:8]}_{safe}" if folder else f"{uuid.uuid4().hex[:8]}_{safe}"


def _get_gcs_bucket():
    try:
        from google.cloud import storage  # 선택적 import
    except ImportError as exc:
        raise StorageError(
            "GCS_BUCKET이 설정되었지만 google-cloud-storage 패키지가 없습니다. "
            "requirements.txt의 주석을 해제하고 설치하세요."
        ) from exc
    client = storage.Client()
    return client.bucket(GCS_BUCKET)


def save_file(content: bytes, filename: str, folder: str = "documents") -> str:
    """파일 저장 후 file_url(경로) 반환.

    - Dropbox(설정 시): "dropbox:{DROPBOX_ROOT}/{folder}/{uuid8}_{파일명}"
    - GCS: "gs://{bucket}/{object}"
    - 로컬: uploads/ 하위 상대 경로 (예: "documents/ab12cd34_report.pdf")
    """
    object_name = _object_name(filename, folder)

    if dropbox_storage.is_configured():
        try:
            path = "{0}/{1}".format(dropbox_storage.root(), object_name)
            stored = dropbox_storage.upload(content, path)
            return DROPBOX_SCHEME + stored
        except dropbox_storage.DropboxConfigError as exc:
            raise StorageError(str(exc))

    if GCS_BUCKET:
        bucket = _get_gcs_bucket()
        blob = bucket.blob(object_name)
        blob.upload_from_string(content)
        return f"gs://{GCS_BUCKET}/{object_name}"

    path = os.path.join(LOCAL_UPLOAD_DIR, object_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return object_name


def read_file(file_url: str) -> Optional[bytes]:
    """저장 파일 바이트 반환 — 이메일 첨부용. 없으면 None."""
    if file_url.startswith(DROPBOX_SCHEME):
        try:
            return dropbox_storage.download(file_url[len(DROPBOX_SCHEME):])
        except dropbox_storage.DropboxConfigError as exc:
            raise StorageError(str(exc))

    if file_url.startswith("gs://"):
        if not GCS_BUCKET:
            raise StorageError("GCS_BUCKET 미설정 상태에서 GCS 파일을 읽을 수 없습니다")
        bucket = _get_gcs_bucket()
        object_name = file_url.replace(f"gs://{GCS_BUCKET}/", "", 1)
        blob = bucket.blob(object_name)
        if not blob.exists():
            return None
        return blob.download_as_bytes()

    path = os.path.join(LOCAL_UPLOAD_DIR, file_url)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def delete_file(file_url: str) -> bool:
    """저장 파일 삭제. 존재하지 않으면 False."""
    if file_url.startswith(DROPBOX_SCHEME):
        try:
            return dropbox_storage.delete(file_url[len(DROPBOX_SCHEME):])
        except dropbox_storage.DropboxConfigError as exc:
            raise StorageError(str(exc))

    if file_url.startswith("gs://"):
        if not GCS_BUCKET:
            raise StorageError("GCS_BUCKET 미설정 상태에서 GCS 경로를 삭제할 수 없습니다")
        bucket = _get_gcs_bucket()
        object_name = file_url.replace(f"gs://{GCS_BUCKET}/", "", 1)
        blob = bucket.blob(object_name)
        if not blob.exists():
            return False
        blob.delete()
        return True

    path = os.path.join(LOCAL_UPLOAD_DIR, file_url)
    if not os.path.isfile(path):
        return False
    os.remove(path)
    return True


def get_url(file_url: str, expires_seconds: int = 3600) -> Optional[str]:
    """다운로드 가능 URL 반환 — Dropbox는 4시간 임시 링크(요청 시점 발급),
    GCS는 서명 URL, 로컬은 절대 경로."""
    if file_url.startswith(DROPBOX_SCHEME):
        try:
            return dropbox_storage.temporary_link(file_url[len(DROPBOX_SCHEME):])
        except dropbox_storage.DropboxConfigError as exc:
            raise StorageError(str(exc))

    if file_url.startswith("gs://"):
        if not GCS_BUCKET:
            raise StorageError("GCS_BUCKET 미설정 상태에서 GCS URL을 생성할 수 없습니다")
        from datetime import timedelta

        bucket = _get_gcs_bucket()
        object_name = file_url.replace(f"gs://{GCS_BUCKET}/", "", 1)
        blob = bucket.blob(object_name)
        return blob.generate_signed_url(expiration=timedelta(seconds=expires_seconds))

    path = os.path.join(LOCAL_UPLOAD_DIR, file_url)
    return path if os.path.isfile(path) else None
