"""사용자 계정 관리 — SCR-14 계정 관리 탭 (CR-1: 가입 승인 모델) + C2 token_version."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_role
from models import User, get_db
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/users", tags=["users"])


def _user_out(user: User) -> schemas.UserOut:
    out = schemas.UserOut.model_validate(user, from_attributes=True)
    return out.model_copy(update={"pin_set": bool(user.pin_hash)})


def _get_target_user(user_id: str, db: Session) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return user


@router.get("/me", response_model=schemas.UserOut)
def get_me(user: User = Depends(get_current_user)):
    return _user_out(user)


@router.get("", response_model=List[schemas.UserOut])
def list_users(
    status: Optional[str] = Query(None, description="PENDING/ACTIVE/INACTIVE"),
    role: Optional[str] = Query(None, description="ADMIN/MANAGER/STAFF"),
    _: User = Depends(require_role("MANAGER")),
    db: Session = Depends(get_db),
):
    query = db.query(User)
    if status:
        query = query.filter(User.status == status)
    if role:
        query = query.filter(User.role == role)
    return [_user_out(u) for u in query.order_by(User.created_at.asc()).all()]


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(
    payload: schemas.UserCreateRequest,
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """관리자 직접 계정 생성 — 가입 신청 없이 즉시 ACTIVE.

    생성된 직원은 이메일 로그인 후 최초 PIN 설정을 거친다.
    """
    from auth import ALLOWED_EMAIL_DOMAIN

    email = payload.email.strip().lower()
    if not email.endswith("@{0}".format(ALLOWED_EMAIL_DOMAIN)):
        raise HTTPException(
            status_code=422,
            detail="회사 도메인(@{0}) 이메일만 등록할 수 있습니다".format(ALLOWED_EMAIL_DOMAIN),
        )
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="이미 등록된 이메일입니다")

    user = User(
        email=email,
        name=payload.name or email.split("@")[0],
        position=payload.position,
        auth_provider="EMAIL",
        role=payload.role,
        status="ACTIVE",
    )
    db.add(user)
    db.flush()
    AuditLogger.user_create(db, admin.user_id, user.user_id, payload.role)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.put("/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: str,
    payload: schemas.UserUpdateRequest,
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """계정 정보 수정 — 이름·직급만 (역할·상태는 전용 엔드포인트)."""
    target = _get_target_user(user_id, db)
    changes = []
    if payload.name is not None and payload.name.strip() and payload.name != target.name:
        changes.append("name: {0}→{1}".format(target.name, payload.name.strip()))
        target.name = payload.name.strip()
    if payload.position is not None and payload.position != (target.position or ""):
        changes.append("position: {0}→{1}".format(target.position or "-", payload.position or "-"))
        target.position = payload.position.strip() or None
    if changes:
        AuditLogger.user_update(db, admin.user_id, target.user_id, ", ".join(changes))
        db.commit()
        db.refresh(target)
    return _user_out(target)


@router.put("/{user_id}/reactivate", response_model=schemas.UserOut)
def reactivate_user(
    user_id: str,
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """비활성 계정 재활성화 — INACTIVE → ACTIVE."""
    target = _get_target_user(user_id, db)
    if target.status != "INACTIVE":
        raise HTTPException(status_code=409, detail="비활성(INACTIVE) 상태의 사용자가 아닙니다")
    target.status = "ACTIVE"
    AuditLogger.user_reactivate(db, admin.user_id, target.user_id)
    db.commit()
    db.refresh(target)
    return _user_out(target)


@router.put("/{user_id}/approve", response_model=schemas.UserOut)
def approve_user(
    user_id: str,
    payload: schemas.UserApproveRequest,
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """가입 승인 (CR-1): PENDING → ACTIVE + role 지정."""
    target = _get_target_user(user_id, db)
    if target.status != "PENDING":
        raise HTTPException(status_code=409, detail="승인 대기(PENDING) 상태의 사용자가 아닙니다")
    target.status = "ACTIVE"
    target.role = payload.role
    AuditLogger.user_approve(db, admin.user_id, target.user_id, payload.role)
    db.commit()
    db.refresh(target)
    return _user_out(target)


@router.put("/{user_id}/role", response_model=schemas.UserOut)
def change_role(
    user_id: str,
    payload: schemas.UserRoleRequest,
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """role 변경 — 본인 불가, token_version+1 로 기발급 토큰 즉시 무효화 (C2)."""
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="본인의 역할은 변경할 수 없습니다")
    target = _get_target_user(user_id, db)
    if target.role != payload.role:
        old_role = target.role
        target.role = payload.role
        target.token_version = (target.token_version or 0) + 1
        AuditLogger.user_role_change(db, admin.user_id, target.user_id, old_role, payload.role)
        db.commit()
        db.refresh(target)
    return _user_out(target)


@router.put("/{user_id}/deactivate", response_model=schemas.UserOut)
def deactivate_user(
    user_id: str,
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """비활성화 — 마지막 ADMIN 차단, token_version+1 (C2)."""
    target = _get_target_user(user_id, db)
    if target.status == "INACTIVE":
        raise HTTPException(status_code=409, detail="이미 비활성화된 사용자입니다")
    if target.role == "ADMIN":
        active_admins = (
            db.query(User).filter(User.role == "ADMIN", User.status == "ACTIVE").count()
        )
        if active_admins <= 1:
            raise HTTPException(status_code=400, detail="마지막 ADMIN 계정은 비활성화할 수 없습니다")
    old_status = target.status
    target.status = "INACTIVE"
    target.token_version = (target.token_version or 0) + 1
    AuditLogger.user_deactivate(db, admin.user_id, target.user_id, old_status)
    db.commit()
    db.refresh(target)
    return _user_out(target)


@router.put("/{user_id}/pin-reset", response_model=schemas.UserOut)
def reset_pin(
    user_id: str,
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """PIN 초기화 (CR-1: 비밀번호 초기화 폐지 — PIN 초기화만 유지)."""
    target = _get_target_user(user_id, db)
    target.pin_hash = None
    AuditLogger.user_pin_reset(db, admin.user_id, target.user_id)
    db.commit()
    db.refresh(target)
    return _user_out(target)
