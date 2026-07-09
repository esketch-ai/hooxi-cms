"""데이터베이스 백업·복구 — SCR-14 (ADMIN 전용).

- 백업 정책: Cloud SQL 자동 백업 매일 05:00 KST(UTC 20:00), 15개 보관 —
  인스턴스 설정으로 관리(본 라우터는 조회·수동 백업·복구).
- 복구는 인스턴스 전체를 해당 백업 시점으로 되돌린다(복구 중 서비스 중단,
  시점 이후 데이터 소실) — 프론트 2단 확인 + 감사 로그 필수.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import schemas
from auth import require_role
from models import User, get_db
from services import gcp_sql
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/backups", tags=["backups"])

BACKUP_POLICY = {
    "schedule": "매일 05:00 (KST)",
    "retention_days": 15,
}


def _guard(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except gcp_sql.GcpSqlConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


def _run_out(item: dict) -> schemas.BackupRunOut:
    return schemas.BackupRunOut(
        backup_run_id=str(item.get("id", "")),
        backup_type=item.get("type"),          # AUTOMATED / ON_DEMAND
        status=item.get("status"),             # SUCCESSFUL / FAILED / RUNNING ...
        start_time=item.get("startTime"),
        end_time=item.get("endTime"),
        description=item.get("description"),
    )


@router.get("", response_model=schemas.BackupListResponse)
def list_backups(
    _: User = Depends(require_role("ADMIN")),
):
    """백업 목록 — 최근순(자동+수동). 일자별 선택 복구의 소스."""
    items = _guard(gcp_sql.list_backup_runs)
    return schemas.BackupListResponse(
        policy=BACKUP_POLICY, items=[_run_out(i) for i in items]
    )


@router.post("", response_model=schemas.BackupOperationOut, status_code=202)
def create_backup(
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """수동 백업 시작 (감사 로그 기록)."""
    op = _guard(gcp_sql.create_backup, "CMS 수동 백업 — {0}".format(admin.email))
    AuditLogger.backup_create(db, admin.user_id)
    db.commit()
    return schemas.BackupOperationOut(
        operation_id=op.get("name", ""), status=op.get("status", "PENDING")
    )


@router.post("/{backup_run_id}/restore", response_model=schemas.BackupOperationOut, status_code=202)
def restore_backup(
    backup_run_id: str,
    payload: schemas.BackupRestoreRequest,
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """일자 선택 복구 — 확인 문구('복구') 필수. 복구 중 서비스가 중단된다."""
    if payload.confirm.strip() != "복구":
        raise HTTPException(status_code=422, detail="확인 문구('복구')가 일치하지 않습니다")
    op = _guard(gcp_sql.restore_backup, backup_run_id)
    AuditLogger.backup_restore(db, admin.user_id, backup_run_id, payload.backup_date or "")
    db.commit()
    return schemas.BackupOperationOut(
        operation_id=op.get("name", ""), status=op.get("status", "PENDING")
    )


@router.get("/operations/{operation_id}", response_model=schemas.BackupOperationOut)
def get_operation(
    operation_id: str,
    _: User = Depends(require_role("ADMIN")),
):
    """백업/복구 작업 진행 상태 폴링 — PENDING/RUNNING/DONE."""
    op = _guard(gcp_sql.get_operation, operation_id)
    error = op.get("error") or {}
    errors = error.get("errors") or []
    return schemas.BackupOperationOut(
        operation_id=op.get("name", ""),
        status=op.get("status", "PENDING"),
        error=errors[0].get("message") if errors else None,
    )
