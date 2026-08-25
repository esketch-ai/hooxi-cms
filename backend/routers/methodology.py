"""방법론 상수 마스터(effective-dated) — 순발열량·배출계수·기술향상계수·전력계수·GWP(D5).

감축량 산정 공식 상수를 하드코딩 없이 관리. 조회 내부 인증, 등록 master.write.
현재값 = key별 유효일자 ≤ 오늘 최신(services.reduction_calc.load_constants 재사용).
"""

from datetime import date
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import MethodologyConstant, User, get_db
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/methodology-constants", tags=["methodology"])


@router.get("", response_model=List[schemas.MethodologyConstantOut])
def list_constants(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(MethodologyConstant)
        .order_by(MethodologyConstant.key, MethodologyConstant.effective_date.desc(),
                  MethodologyConstant.created_at.desc())
        .all()
    )


@router.get("/current", response_model=List[schemas.MethodologyConstantOut])
def current_constants(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(MethodologyConstant)
        .filter(MethodologyConstant.effective_date <= date.today())
        .order_by(MethodologyConstant.key, MethodologyConstant.effective_date.desc(),
                  MethodologyConstant.created_at.desc())
        .all()
    )
    seen, cur = set(), []
    for r in rows:
        if r.key in seen:
            continue
        seen.add(r.key)
        cur.append(r)
    return cur


@router.post("", response_model=schemas.MethodologyConstantOut, status_code=201)
def create_constant(
    payload: schemas.MethodologyConstantIn,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """상수 등록 — 같은 key·유효일자 append 허용(이력 보존)."""
    c = MethodologyConstant(
        key=payload.key.strip(), value=payload.value, unit=(payload.unit or "").strip() or None,
        label=(payload.label or "").strip() or None, effective_date=payload.effective_date,
        note=payload.note, created_by=user.user_id,
    )
    db.add(c)
    db.flush()
    AuditLogger.log_action(
        db, user.user_id, "METHODOLOGY_CONSTANT_CREATE",
        target_type="METHODOLOGY_CONSTANT", target_id=c.const_id,
        new_value="{0}={1}".format(c.key, c.value),
    )
    db.commit()
    db.refresh(c)
    return c
