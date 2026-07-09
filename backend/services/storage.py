"""파일 저장소 — GCS_BUCKET 설정 시 Google Cloud Storage, 미설정 시 로컬 uploads/ 폴백.

DB(tb_document.file_url)에는 본 모듈이 반환하는 경로/URL만 저장한다 (Server.pdf §3).
google-cloud-storage는 선택적 import — 미설치 로컬 환경에서도 앱이 뜬다.
"""

import os
import re
import uuid
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))

GCS_BUCKET = os.getenv("GCS_BUCKET")


class StorageError(RuntimeError):
    pass


def _sanitize_filename(filename: str) -> str:
    name = os.path.basename(filename or "file")
    return re.sub(r"[^\w.\-가-힣]", "_", name)


def _object_name(filename: str, folder: str) -> str:
    safe = _sanitize_filename(filename)
    folder = folder.strip("/")
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

    - GCS: "gs://{bucket}/{object}" 형태로 저장 경로 반환
    - 로컬: uploads/ 하위 상대 경로 반환 (예: "documents/ab12cd34_report.pdf")
    """
    object_name = _object_name(filename, folder)

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
    """다운로드 가능 URL 반환 — GCS는 서명 URL, 로컬은 절대 경로."""
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
