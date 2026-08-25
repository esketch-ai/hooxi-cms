"""차량 통합 상세(dossier, 개편 P5) — 한 vehicle_no의 전 생애 조회.

GET /vehicles/{vehicle_no}/dossier — 보유·참여·레지스트리·산정·3단계·로그·재무를 한 번에.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user
from models import User, get_db
from services import vehicle_dossier as vd

router = APIRouter(tags=["vehicle-dossier"])


@router.get("/vehicles/{vehicle_no}/dossier", response_model=schemas.VehicleDossierOut)
def vehicle_dossier(
    vehicle_no: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """차량번호로 전 모델을 모아 통합 상세 반환(읽기 전용 조립)."""
    return schemas.VehicleDossierOut(**vd.get_dossier(db, vehicle_no))
