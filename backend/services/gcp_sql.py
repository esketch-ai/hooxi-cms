"""Cloud SQL Admin API 클라이언트 — 백업 목록·수동 백업·일자 선택 복구.

- 인증: Cloud Run 메타데이터 서버에서 런타임 서비스 계정 액세스 토큰 취득
  (신규 의존성 없음 — httpx만 사용). 로컬 등 메타데이터 서버가 없는 환경은
  GcpSqlConfigError → 호출부 503 게이트 (email_service 패턴).
- env: GCP_PROJECT / CLOUDSQL_INSTANCE 미설정 시 기능 비활성.
- 백업 정책 자체(매일 05:00 KST, 15개 보관)는 인스턴스 설정으로 관리 —
  본 모듈은 조회·수동 백업·복구만 담당한다.
"""

import os
from typing import Optional

import httpx

_METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
_SQLADMIN_BASE = "https://sqladmin.googleapis.com/v1"


class GcpSqlConfigError(RuntimeError):
    """Cloud SQL 백업 연동 미설정/불가 — 호출부에서 503으로 변환."""


def _project() -> Optional[str]:
    return os.getenv("GCP_PROJECT")


def _instance() -> Optional[str]:
    return os.getenv("CLOUDSQL_INSTANCE")


def is_configured() -> bool:
    return bool(_project() and _instance())


def _require_config():
    if not is_configured():
        raise GcpSqlConfigError(
            "Cloud SQL 백업 연동이 설정되지 않았습니다. "
            "GCP_PROJECT / CLOUDSQL_INSTANCE 환경변수를 설정하세요."
        )


def _access_token() -> str:
    """메타데이터 서버에서 런타임 SA 토큰 취득 (Cloud Run/GCE 전용)."""
    try:
        resp = httpx.get(
            _METADATA_TOKEN_URL, headers={"Metadata-Flavor": "Google"}, timeout=5.0
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except Exception as exc:
        raise GcpSqlConfigError(
            "GCP 자격 증명을 얻지 못했습니다 (Cloud Run 환경에서만 지원): {0}".format(exc)
        )


def _request(method: str, path: str, json_body: Optional[dict] = None) -> dict:
    _require_config()
    token = _access_token()
    url = "{0}/projects/{1}{2}".format(_SQLADMIN_BASE, _project(), path)
    resp = httpx.request(
        method,
        url,
        json=json_body,
        headers={"Authorization": "Bearer {0}".format(token)},
        timeout=30.0,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            "Cloud SQL API 오류 ({0}): {1}".format(resp.status_code, resp.text[:300])
        )
    return resp.json()


def list_backup_runs(max_results: int = 30) -> list:
    """백업 실행 목록 — 최근순. AUTOMATED/ON_DEMAND 포함."""
    data = _request(
        "GET", "/instances/{0}/backupRuns?maxResults={1}".format(_instance(), max_results)
    )
    return data.get("items", [])


def create_backup(description: str = "") -> dict:
    """수동(온디맨드) 백업 시작 — operation 반환."""
    return _request(
        "POST",
        "/instances/{0}/backupRuns".format(_instance()),
        json_body={"description": description or "CMS 수동 백업"},
    )


def restore_backup(backup_run_id: str) -> dict:
    """지정 백업으로 인스턴스 복구 — operation 반환.

    주의: 인스턴스 전체가 해당 시점으로 되돌아가며 복구 중 서비스가 중단된다.
    """
    return _request(
        "POST",
        "/instances/{0}/restoreBackup".format(_instance()),
        json_body={
            "restoreBackupContext": {
                "backupRunId": backup_run_id,
                "instanceId": _instance(),
                "project": _project(),
            }
        },
    )


def get_operation(operation_id: str) -> dict:
    """작업(백업/복구) 진행 상태 조회 — status: PENDING/RUNNING/DONE (+error)."""
    return _request("GET", "/operations/{0}".format(operation_id))
