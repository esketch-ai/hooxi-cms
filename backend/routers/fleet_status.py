"""운수사 계약대수 현황(F2/F3) — 원본 엑셀 업로드·월별 추이·수작업 관리.

- 업로드: 원본 탭 전용 파서(services/fleet_import) → 지역+회사명 매칭·다중 사업장 합산·
  (고객사×월) upsert. preview(무변경) → commit. 권한 master.write.
- 현황 탭: 고객사별 월별 대수 추이(tb_fleet_status) + 수작업 관리(tb_fleet_mgmt) 조회/저장.
  수작업은 업로드와 독립(재업로드가 덮지 않음).
- 감사 로그엔 건수 요약만(원문·비밀값 금지 — R2-E6).
"""

import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

import schemas
from auth import require_permission
from models import Client, FleetMgmt, FleetStatus, User, get_db
from services import fleet_import
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/fleet-status", tags=["fleet-status"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


async def _read_upload(file: UploadFile) -> bytes:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="빈 파일은 업로드할 수 없습니다")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기가 25MB를 초과합니다")
    return content


def _validate_period(period: str) -> str:
    period = (period or "").strip()
    if not _PERIOD_RE.match(period):
        raise HTTPException(status_code=422, detail="대상 월 형식은 YYYY-MM 입니다 (예: 2026-06)")
    return period


@router.post("/preview", response_model=schemas.FleetStatusPreviewOut)
async def preview_fleet_status(
    period: str = Form(...),
    file: UploadFile = File(...),
    _: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """미리보기 — 합산·매칭·신규/갱신 판정만 반환(DB 무변경)."""
    period = _validate_period(period)
    content = await _read_upload(file)
    return fleet_import.analyze(db, content, period)


@router.post("/commit", response_model=schemas.FleetStatusCommitOut)
async def commit_fleet_status(
    period: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """반영 — (고객사×월) upsert. 같은 월 재업로드는 대수 갱신(중복 생성 없음)."""
    period = _validate_period(period)
    content = await _read_upload(file)
    result = fleet_import.commit(db, content, period, actor_id=user.user_id)
    AuditLogger.log_action(
        db,
        user.user_id,
        "FLEET_STATUS_IMPORT",
        target_type="FLEET_STATUS",
        new_value="운수사 계약대수 현황({0}) 업로드 — 생성 {1}건 / 갱신 {2}건 / 미매칭 {3}건".format(
            period, result["created"], result["updated"], result["unmatched"]
        ),
    )
    db.commit()
    return result


@router.get("/client/{client_id}", response_model=schemas.FleetClientStatusOut)
def get_client_fleet_status(
    client_id: str,
    _: User = Depends(require_permission("crm.read_write")),
    db: Session = Depends(get_db),
):
    """현황 탭 — 고객사 월별 대수 추이(최신 월 우선) + 수작업 관리."""
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="고객사를 찾을 수 없습니다")
    rows = (
        db.query(FleetStatus)
        .filter(FleetStatus.client_id == client_id)
        .order_by(FleetStatus.period.desc())
        .all()
    )
    trend = [
        schemas.FleetStatusTrendItem(
            period=r.period, license_count=r.license_count, total_count=r.total_count,
            diesel=r.diesel, cng=r.cng, hybrid=r.hybrid, electric=r.electric,
            hydrogen=r.hydrogen, region=r.region, industry=r.industry,
        )
        for r in rows
    ]
    mgmt = db.get(FleetMgmt, client_id)
    mgmt_out = (
        schemas.FleetMgmtOut(
            client_id=client_id, target_type=mgmt.target_type, contract_yn=mgmt.contract_yn,
            union_contract=mgmt.union_contract, regulated_yn=mgmt.regulated_yn, memo=mgmt.memo,
        )
        if mgmt else None
    )
    return schemas.FleetClientStatusOut(client_id=client_id, trend=trend, mgmt=mgmt_out)


@router.put("/client/{client_id}/mgmt", response_model=schemas.FleetMgmtOut)
def update_client_fleet_mgmt(
    client_id: str,
    payload: schemas.FleetMgmtIn,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """수작업 관리 저장(업로드와 독립) — 없으면 생성, 있으면 갱신."""
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="고객사를 찾을 수 없습니다")
    mgmt = db.get(FleetMgmt, client_id)
    if mgmt is None:
        mgmt = FleetMgmt(client_id=client_id)
        db.add(mgmt)
    for f in ("target_type", "contract_yn", "union_contract", "regulated_yn", "memo"):
        setattr(mgmt, f, getattr(payload, f))
    mgmt.updated_by = user.user_id
    AuditLogger.log_action(
        db, user.user_id, "FLEET_MGMT_UPDATE",
        target_type="FLEET_MGMT", target_id=client_id,
        new_value="계약여부={0}/대상={1}".format(payload.contract_yn, payload.target_type),
    )
    db.commit()
    return schemas.FleetMgmtOut(
        client_id=client_id, target_type=mgmt.target_type, contract_yn=mgmt.contract_yn,
        union_contract=mgmt.union_contract, regulated_yn=mgmt.regulated_yn, memo=mgmt.memo,
    )
