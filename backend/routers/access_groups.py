"""접근 그룹 관리(G3) — 그룹 CRUD·메뉴 배정·사용자 배정·모드 스위치. ADMIN 전용.

메뉴 키 정본은 access_control.MENU_KEYS — 없는 키는 저장 시 걸러진다(오타 방어).
기본(전사) 그룹은 삭제·기본해제 금지(그룹 미배정 사용자의 fail-safe 소속).
감사 로그에는 이름·건수·모드만(비밀값 금지 R2-E6).
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import schemas
from access_control import (
    ACCESS_CONTROL_MODE_KEY,
    ACCESS_CONTROL_MODES,
    MENU_KEYS,
    get_access_mode,
    valid_menu_keys,
)
from auth import require_permission
from models import AccessGroup, Config, GroupMenu, User, UserGroup, get_db
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/access-groups", tags=["access-groups"])

_admin = require_permission("admin.users_config_backup")


def _group_out(db: Session, g: AccessGroup) -> schemas.AccessGroupOut:
    menus = [m.menu_key for m in db.query(GroupMenu).filter_by(group_id=g.group_id).all()]
    member_ids = [ug.user_id for ug in db.query(UserGroup).filter_by(group_id=g.group_id).all()]
    return schemas.AccessGroupOut(
        group_id=g.group_id, name=g.name, home_path=g.home_path,
        is_default=bool(g.is_default), memo=g.memo,
        menus=[k for k in MENU_KEYS if k in set(menus)], member_ids=member_ids,
    )


@router.get("/meta", response_model=schemas.AccessGroupMeta)
def access_meta(_: User = Depends(_admin), db: Session = Depends(get_db)):
    """관리 UI 메타 — 메뉴 키 정본·현재 모드·가능 모드."""
    return schemas.AccessGroupMeta(
        menu_keys=list(MENU_KEYS), mode=get_access_mode(db), modes=list(ACCESS_CONTROL_MODES),
    )


@router.put("/mode", response_model=schemas.AccessGroupMeta)
def set_access_mode(
    payload: schemas.AccessModeIn,
    user: User = Depends(_admin),
    db: Session = Depends(get_db),
):
    """모드 전환 — off(무동작)/monitor(감사로그만)/enforce(403 차단)."""
    mode = payload.mode.strip().lower()
    if mode not in ACCESS_CONTROL_MODES:
        raise HTTPException(status_code=422, detail="mode는 off/monitor/enforce 중 하나입니다")
    row = db.get(Config, ACCESS_CONTROL_MODE_KEY)
    old = get_access_mode(db)
    if row is None:
        row = Config(config_key=ACCESS_CONTROL_MODE_KEY,
                     description="그룹 메뉴 접근제어 모드(off/monitor/enforce)")
        db.add(row)
    row.config_value = '"{0}"'.format(mode)
    row.updated_by = user.user_id
    AuditLogger.log_action(db, user.user_id, "ACCESS_MODE_CHANGE",
                           target_type="ACCESS_CONTROL", old_value=old, new_value=mode)
    db.commit()
    return access_meta(user, db)


@router.get("", response_model=List[schemas.AccessGroupOut])
def list_groups(_: User = Depends(_admin), db: Session = Depends(get_db)):
    groups = db.query(AccessGroup).order_by(AccessGroup.is_default.desc(), AccessGroup.name).all()
    return [_group_out(db, g) for g in groups]


@router.post("", response_model=schemas.AccessGroupOut, status_code=201)
def create_group(
    payload: schemas.AccessGroupIn,
    user: User = Depends(_admin),
    db: Session = Depends(get_db),
):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="그룹명은 필수입니다")
    if db.query(AccessGroup).filter_by(name=name).first():
        raise HTTPException(status_code=409, detail="같은 이름의 그룹이 이미 있습니다")
    g = AccessGroup(name=name, home_path=payload.home_path or "/dashboard", memo=payload.memo)
    db.add(g)
    db.flush()
    for key in valid_menu_keys(payload.menus or []):
        db.add(GroupMenu(group_id=g.group_id, menu_key=key))
    AuditLogger.log_action(db, user.user_id, "ACCESS_GROUP_CREATE",
                           target_type="ACCESS_GROUP", target_id=g.group_id,
                           new_value="{0} (메뉴 {1}개)".format(name, len(payload.menus or [])))
    db.commit()
    return _group_out(db, g)


@router.put("/{group_id}", response_model=schemas.AccessGroupOut)
def update_group(
    group_id: str,
    payload: schemas.AccessGroupIn,
    user: User = Depends(_admin),
    db: Session = Depends(get_db),
):
    g = db.get(AccessGroup, group_id)
    if g is None:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="그룹명은 필수입니다")
    dup = db.query(AccessGroup).filter(AccessGroup.name == name,
                                       AccessGroup.group_id != group_id).first()
    if dup:
        raise HTTPException(status_code=409, detail="같은 이름의 그룹이 이미 있습니다")
    g.name = name
    g.home_path = payload.home_path or g.home_path or "/dashboard"
    g.memo = payload.memo
    # 메뉴 전체 교체 — 기본(전사) 그룹은 전 메뉴 고정(축소 금지: fail-safe 훼손 방지)
    if not g.is_default:
        db.query(GroupMenu).filter_by(group_id=group_id).delete(synchronize_session=False)
        for key in valid_menu_keys(payload.menus or []):
            db.add(GroupMenu(group_id=group_id, menu_key=key))
    AuditLogger.log_action(db, user.user_id, "ACCESS_GROUP_UPDATE",
                           target_type="ACCESS_GROUP", target_id=group_id,
                           new_value="{0} (메뉴 {1}개)".format(name, len(payload.menus or [])))
    db.commit()
    return _group_out(db, g)


@router.delete("/{group_id}", status_code=204)
def delete_group(
    group_id: str,
    user: User = Depends(_admin),
    db: Session = Depends(get_db),
):
    g = db.get(AccessGroup, group_id)
    if g is None:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")
    if g.is_default:
        raise HTTPException(status_code=422, detail="기본(전사) 그룹은 삭제할 수 없습니다")
    AuditLogger.log_action(db, user.user_id, "ACCESS_GROUP_DELETE",
                           target_type="ACCESS_GROUP", target_id=group_id, old_value=g.name)
    db.delete(g)  # tb_group_menu·tb_user_group은 FK CASCADE
    db.commit()


@router.put("/users/{user_id}", response_model=List[str])
def assign_user_groups(
    user_id: str,
    payload: schemas.UserGroupsIn,
    user: User = Depends(_admin),
    db: Session = Depends(get_db),
):
    """사용자 그룹 배정(전체 교체) — 빈 목록이면 미배정(=전사 암묵 상속)."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    group_ids = list(dict.fromkeys(payload.group_ids or []))
    if group_ids:
        found = {g.group_id for g in db.query(AccessGroup)
                 .filter(AccessGroup.group_id.in_(group_ids)).all()}
        missing = [g for g in group_ids if g not in found]
        if missing:
            raise HTTPException(status_code=422, detail="존재하지 않는 그룹이 있습니다")
    db.query(UserGroup).filter_by(user_id=user_id).delete(synchronize_session=False)
    for gid in group_ids:
        db.add(UserGroup(user_id=user_id, group_id=gid))
    AuditLogger.log_action(db, user.user_id, "ACCESS_GROUP_ASSIGN",
                           target_type="USER", target_id=user_id,
                           new_value="그룹 {0}개 배정".format(len(group_ids)))
    db.commit()
    return group_ids
