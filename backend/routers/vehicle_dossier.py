"""차량 통합 상세(dossier, 개편 P5) — 한 vehicle_no의 전 생애 조회.

GET /vehicles/{vehicle_no}/dossier — 보유·참여·레지스트리·산정·3단계·로그·재무를 한 번에.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import User, get_db
from services import vehicle_dossier as vd
from services import vehicle_link as vl
from services.audit_logger import AuditLogger

router = APIRouter(tags=["vehicle-dossier"])


@router.get("/vehicles/{vehicle_no}/dossier", response_model=schemas.VehicleDossierOut)
def vehicle_dossier(
    vehicle_no: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """차량번호로 전 모델을 모아 통합 상세 반환(읽기 전용 조립)."""
    return schemas.VehicleDossierOut(**vd.get_dossier(db, vehicle_no))


@router.post("/vehicles/link-backfill", response_model=schemas.VehicleLinkResult)
def link_backfill(
    overwrite: bool = Query(False, description="이미 링크된 것도 재매칭"),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """레지스트리·산정 입력의 client_vehicle_id를 보유차량 원장에 백필(VIN 우선). 멱등."""
    out = vl.link_vehicles(db, overwrite=overwrite)
    AuditLogger.log_action(
        db, user.user_id, "VEHICLE_LINK_BACKFILL", target_type="BATCH",
        new_value="registry_linked={0}, calc_linked={1}".format(
            out["registry"]["linked"], out["calc_input"]["linked"]),
    )
    db.commit()
    return schemas.VehicleLinkResult(registry=out["registry"], calc_input=out["calc_input"])
