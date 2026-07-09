"""사용자 계정 관리 — SCR-14 계정 관리 탭 (CR-1: 가입 승인 모델) + C2 token_version."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_role
from models import User, get_db

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


@router.put("/{user_id}/approve", response_model=schemas.UserOut)
def approve_user(
    user_id: str,
    payload: schemas.UserApproveRequest,
    _: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """가입 승인 (CR-1): PENDING → ACTIVE + role 지정."""
    target = _get_target_user(user_id, db)
    if target.status != "PENDING":
        raise HTTPException(status_code=409, detail="승인 대기(PENDING) 상태의 사용자가 아닙니다")
    target.status = "ACTIVE"
    target.role = payload.role
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
        target.role = payload.role
        target.token_version = (target.token_version or 0) + 1
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
    target.status = "INACTIVE"
    target.token_version = (target.token_version or 0) + 1
    db.commit()
    db.refresh(target)
    return _user_out(target)


@router.put("/{user_id}/pin-reset", response_model=schemas.UserOut)
def reset_pin(
    user_id: str,
    _: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """PIN 초기화 (CR-1: 비밀번호 초기화 폐지 — PIN 초기화만 유지)."""
    target = _get_target_user(user_id, db)
    target.pin_hash = None
    db.commit()
    db.refresh(target)
    return _user_out(target)
