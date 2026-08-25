"""충전 인프라(차고지·충전기·AC전력량계) — MRV 증빙 원장(D3, 증빙 02).

- POST /charging-infra/import : 지역 충전기 제원 엑셀 업로드 → 해당 권역 교체 적재(멱등)
- GET  /charging-infra         : 차고지 목록(충전기·계 수 포함, 권역·운수사·검색 필터)
- GET  /charging-infra/summary : 차고지·충전기·전력량계 총수 + 권역별
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import AcPowerMeter, Charger, ChargingFacility, User, get_db
from routers import common
from services import charging_infra_import as cii
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/charging-infra", tags=["charging-infra"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.post("/import", response_model=schemas.ChargingInfraImportResult)
async def import_charging_infra(
    file: UploadFile = File(...),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """충전기 제원 엑셀 → 차고지·충전기·계 적재(파일 권역만 교체, 멱등)."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="빈 파일은 업로드할 수 없습니다")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기가 25MB를 초과합니다")
    try:
        facilities = cii.parse_charging_infra(content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="엑셀 파싱 실패: {0}".format(exc))
    if not facilities:
        raise HTTPException(status_code=422, detail="충전기 제원 시트를 찾지 못했습니다")
    result = cii.apply_charging_infra(db, facilities, replace=True)
    AuditLogger.log_action(
        db, user.user_id, "CHARGING_INFRA_IMPORT", target_type="BATCH",
        new_value="fac={0}, chg={1}, mtr={2}".format(
            result["facilities"], result["chargers"], result["meters"]),
    )
    db.commit()
    return schemas.ChargingInfraImportResult(**result)


@router.get("", response_model=schemas.ChargingFacilityListResponse)
def list_facilities(
    region: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="운수사·주소 검색"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(ChargingFacility)
    if region:
        q = q.filter(ChargingFacility.region == region)
    if client_id:
        q = q.filter(ChargingFacility.client_id == client_id)
    if search:
        like = "%{0}%".format(search.strip())
        q = q.filter((ChargingFacility.operator_name.like(like)) | (ChargingFacility.address.like(like)))
    total = q.count()
    facs = (
        q.order_by(ChargingFacility.region, ChargingFacility.operator_name)
        .offset((page - 1) * page_size).limit(page_size).all()
    )
    fac_ids = [f.facility_id for f in facs]
    chg_counts = dict(
        db.query(Charger.facility_id, func.count(Charger.charger_id))
        .filter(Charger.facility_id.in_(fac_ids)).group_by(Charger.facility_id).all()
    ) if fac_ids else {}
    mtr_counts = dict(
        db.query(AcPowerMeter.facility_id, func.count(AcPowerMeter.meter_id))
        .filter(AcPowerMeter.facility_id.in_(fac_ids)).group_by(AcPowerMeter.facility_id).all()
    ) if fac_ids else {}
    cnames = common.client_name_map(db, [f.client_id for f in facs])
    items = [
        schemas.ChargingFacilityOut.model_validate(f).model_copy(update={
            "client_name": cnames.get(f.client_id),
            "charger_count": chg_counts.get(f.facility_id, 0),
            "meter_count": mtr_counts.get(f.facility_id, 0),
        })
        for f in facs
    ]
    return schemas.ChargingFacilityListResponse(items=items, total=total)


@router.get("/summary", response_model=schemas.ChargingInfraSummary)
def charging_summary(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    facs = db.query(ChargingFacility.region).all()
    by_region = {}
    for (region,) in facs:
        rk = region or "미상"
        by_region[rk] = by_region.get(rk, 0) + 1
    return schemas.ChargingInfraSummary(
        facilities=len(facs),
        chargers=db.query(func.count(Charger.charger_id)).scalar() or 0,
        meters=db.query(func.count(AcPowerMeter.meter_id)).scalar() or 0,
        by_region=[{"region": k, "count": v} for k, v in sorted(by_region.items())],
    )
