"""배출계수(EF) 마스터(effective-dated) — 감축량 산정의 연료별 CO2 배출계수 관리(M4).

감축 방법론 상수를 하드코딩하지 않고 마스터로 관리(부록 G/L·데이터화 마스터 플랜).
현재 EF = 연료별 유효일자 ≤ 오늘 중 최신 1건. 이력 보존(과거 산정 재현). 등록은 master.write,
조회는 내부 인증(get_current_user) — 외부역할은 PERMISSION_MATRIX 미등록으로 자동 차단.
"""

from datetime import date
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import EmissionFactor, User, get_db
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/emission-factors", tags=["emission-factors"])


@router.get("", response_model=List[schemas.EmissionFactorOut])
def list_emission_factors(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """EF 이력 목록(연료·유효일자 최신순). 소량 전제 전체 반환."""
    return (
        db.query(EmissionFactor)
        .order_by(
            EmissionFactor.fuel_type.asc(),
            EmissionFactor.effective_date.desc(),
            EmissionFactor.created_at.desc(),
        )
        .all()
    )


@router.get("/current", response_model=List[schemas.EmissionFactorOut])
def current_emission_factors(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """연료별 현재 EF — 유효일자 ≤ 오늘 중 각 연료의 최신 1건."""
    rows = (
        db.query(EmissionFactor)
        .filter(EmissionFactor.effective_date <= date.today())
        .order_by(
            EmissionFactor.fuel_type.asc(),
            EmissionFactor.effective_date.desc(),
            EmissionFactor.created_at.desc(),
        )
        .all()
    )
    seen = set()
    current = []
    for r in rows:
        if r.fuel_type in seen:
            continue
        seen.add(r.fuel_type)
        current.append(r)
    return current


@router.post("", response_model=schemas.EmissionFactorOut, status_code=201)
def create_emission_factor(
    payload: schemas.EmissionFactorIn,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """EF 등록 — 같은 (연료, effective_date) 재등록은 append 허용(이력 보존, 조회는 최신 우선)."""
    ef = EmissionFactor(
        fuel_type=payload.fuel_type.strip(),
        ef_value=payload.ef_value,
        unit=(payload.unit or "").strip() or None,
        effective_date=payload.effective_date,
        note=payload.note,
        created_by=user.user_id,
    )
    db.add(ef)
    db.flush()
    AuditLogger.log_action(
        db, user.user_id, "EMISSION_FACTOR_CREATE",
        target_type="EMISSION_FACTOR", target_id=ef.factor_id,
        new_value="{0}={1}{2}".format(ef.fuel_type, ef.ef_value, ef.unit or ""),
    )
    db.commit()
    db.refresh(ef)
    return ef
