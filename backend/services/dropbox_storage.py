"""Dropbox 저장소 백엔드 — 회사 Dropbox의 /Hooxi-CMS 아래 업체별 서브 폴더 관리.

- 인증: refresh token(만료 없음) + SDK 자동 access token 갱신.
  설정: DROPBOX_APP_KEY / DROPBOX_APP_SECRET / DROPBOX_REFRESH_TOKEN
       DROPBOX_ROOT (선택, 기본 "/Hooxi-CMS")
  — 연동 설정(DB) 우선 + env 폴백 (services/integration_config.resolve)
- 팀 계정(team space) 자동 감지: root_info가 team이면 Path-Root 헤더 적용.
- file_url 스킴: "dropbox:" + Dropbox 절대 경로 (storage.py가 라우팅).
- temporary link(4시간)는 항상 요청 시점 발급 — 저장·캐시 금지.
"""

import time
from typing import Optional

from services import integration_config
from services.integration_config import resolve

_UPLOAD_SINGLE_LIMIT = 150 * 1024 * 1024  # /2/files/upload 한도
_SESSION_CHUNK = 8 * 1024 * 1024  # 4MB 배수 권장

_client = None  # 싱글턴 — 연동 설정 버전이 바뀌면 재생성
_client_version = None  # 클라이언트 생성 시점의 integration_config 버전


class DropboxConfigError(RuntimeError):
    """Dropbox 연동 미설정/초기화 실패."""


def is_configured() -> bool:
    return bool(
        resolve("DROPBOX_APP_KEY")
        and resolve("DROPBOX_APP_SECRET")
        and resolve("DROPBOX_REFRESH_TOKEN")
    )


def root() -> str:
    return (resolve("DROPBOX_ROOT") or "/Hooxi-CMS").rstrip("/")


def _get_client():
    """SDK 클라이언트 싱글턴 — team space면 Path-Root를 루트 네임스페이스로 전환.

    연동 설정 저장(bump_version) 후 첫 호출 시 새 자격증명으로 재생성한다.
    """
    global _client, _client_version
    current_version = integration_config.get_version()
    if _client is not None and _client_version == current_version:
        return _client
    if not is_configured():
        raise DropboxConfigError(
            "Dropbox 연동이 설정되지 않았습니다. "
            "DROPBOX_APP_KEY / DROPBOX_APP_SECRET / DROPBOX_REFRESH_TOKEN 환경변수를 설정하세요."
        )
    import dropbox  # 선택적 import — 미설치 환경(구 이미지)에서도 모듈 로드는 가능

    dbx = dropbox.Dropbox(
        oauth2_refresh_token=resolve("DROPBOX_REFRESH_TOKEN"),
        app_key=resolve("DROPBOX_APP_KEY"),
        app_secret=resolve("DROPBOX_APP_SECRET"),
        timeout=30,
    )
    try:
        account = dbx.users_get_current_account()
        root_info = account.root_info
        # 팀 스페이스: 기본 루트가 멤버 폴더 — 팀 루트 네임스페이스로 승격
        if getattr(root_info, "root_namespace_id", None) and (
            root_info.root_namespace_id != root_info.home_namespace_id
        ):
            dbx = dbx.with_path_root(
                dropbox.common.PathRoot.root(root_info.root_namespace_id)
            )
            print("✓ Dropbox team space 감지 — 팀 루트 네임스페이스 사용")
    except DropboxConfigError:
        raise
    except Exception as exc:
        raise DropboxConfigError("Dropbox 계정 확인에 실패했습니다: {0}".format(exc))
    _client = dbx
    _client_version = current_version
    return _client


def _retry_once(call, *args, **kwargs):
    """429(rate limit) 시 Retry-After 존중 1회 재시도."""
    import dropbox

    try:
        return call(*args, **kwargs)
    except dropbox.exceptions.RateLimitError as exc:
        time.sleep(min(exc.backoff or 1, 10))
        return call(*args, **kwargs)


def upload(content: bytes, path: str) -> str:
    """업로드 — 상위 폴더 자동 생성, 이름 충돌 시 autorename.

    150MB 초과는 upload session으로 분할. 반환: 실제 저장된 Dropbox 경로.
    """
    import dropbox

    dbx = _get_client()
    mode = dropbox.files.WriteMode.add
    if len(content) <= _UPLOAD_SINGLE_LIMIT:
        meta = _retry_once(dbx.files_upload, content, path, mode=mode, autorename=True)
    else:
        session = dbx.files_upload_session_start(content[:_SESSION_CHUNK])
        cursor = dropbox.files.UploadSessionCursor(
            session_id=session.session_id, offset=_SESSION_CHUNK
        )
        offset = _SESSION_CHUNK
        while offset < len(content) - _SESSION_CHUNK:
            dbx.files_upload_session_append_v2(
                content[offset : offset + _SESSION_CHUNK], cursor
            )
            offset += _SESSION_CHUNK
            cursor.offset = offset
        commit = dropbox.files.CommitInfo(path=path, mode=mode, autorename=True)
        meta = dbx.files_upload_session_finish(content[offset:], cursor, commit)
    return meta.path_display or path


def temporary_link(path: str) -> Optional[str]:
    """4시간 유효 임시 다운로드 URL — 요청 시점마다 발급."""
    import dropbox

    dbx = _get_client()
    try:
        return _retry_once(dbx.files_get_temporary_link, path).link
    except dropbox.exceptions.ApiError:
        return None  # 삭제·이동된 파일 — 호출부가 404 처리


def download(path: str) -> Optional[bytes]:
    """파일 바이트 다운로드 (이메일 첨부·로컬 스트림용)."""
    import dropbox

    dbx = _get_client()
    try:
        _, resp = _retry_once(dbx.files_download, path)
        return resp.content
    except dropbox.exceptions.ApiError:
        return None


def delete(path: str) -> bool:
    import dropbox

    dbx = _get_client()
    try:
        _retry_once(dbx.files_delete_v2, path)
        return True
    except dropbox.exceptions.ApiError:
        return False
