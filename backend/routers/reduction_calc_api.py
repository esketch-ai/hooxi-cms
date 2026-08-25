"""차량별 산정 입력 + 전 차량 감축량 계산(D5).

- POST /calc-inputs/import : 크롤링 정규화 엑셀 업로드 → 차량번호 중복체크 후 upsert
- GET  /calc-inputs         : 산정 입력 목록(권역·검색)
- GET  /reduction-run       : 전 차량 계산 결과 + 요약(온-더-플라이)
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import User, VehicleCalcInput, get_db
from routers import common
from services import calc_input_import as cii
from services import reduction_run as rr
from services.audit_logger import AuditLogger

router = APIRouter(tags=["reduction-calc"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.post("/calc-inputs/import", response_model=schemas.CalcInputImportResult)
async def import_calc_inputs(
    file: UploadFile = File(...),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """산정 입력 엑셀 → 차량번호 중복체크 후 upsert(CRUD)."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="빈 파일은 업로드할 수 없습니다")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기가 25MB를 초과합니다")
    try:
        rows = cii.parse_calc_inputs(content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="엑셀 파싱 실패: {0}".format(exc))
    if not rows:
        raise HTTPException(status_code=422, detail="차량번호 열을 찾지 못했습니다(헤더 확인)")
    result = cii.apply_calc_inputs(db, rows)
    AuditLogger.log_action(
        db, user.user_id, "CALC_INPUT_IMPORT", target_type="BATCH",
        new_value="created={0}, updated={1}".format(result["created"], result["updated"]),
    )
    db.commit()
    return schemas.CalcInputImportResult(**result)


@router.get("/calc-inputs", response_model=schemas.CalcInputListResponse)
def list_calc_inputs(
    region: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(VehicleCalcInput)
    if region:
        q = q.filter(VehicleCalcInput.region == region)
    if search:
        like = "%{0}%".format(search.strip())
        q = q.filter((VehicleCalcInput.vehicle_no.like(like)) | (VehicleCalcInput.operator_name.like(like)))
    total = q.count()
    rows = (
        q.order_by(VehicleCalcInput.region, VehicleCalcInput.vehicle_no)
        .offset((page - 1) * page_size).limit(page_size).all()
    )
    cnames = common.client_name_map(db, [r.client_id for r in rows])
    items = [
        schemas.CalcInputOut.model_validate(r).model_copy(
            update={"client_name": cnames.get(r.client_id)})
        for r in rows
    ]
    return schemas.CalcInputListResponse(items=items, total=total)


@router.get("/reduction-run", response_model=schemas.ReductionRunResponse)
def reduction_run(
    region: Optional[str] = Query(None),
    only_ok: bool = Query(False, description="계산 성공 건만"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """전 차량 감축량 계산 — 산정 입력 × 방법론 상수 × 민간비율 → 엔진. 요약 + 차량별."""
    out = rr.run_all(db, region=region)
    results = out["results"]
    if only_ok:
        results = [r for r in results if r["status"] == "OK"]
    cnames = common.client_name_map(db, [r.get("client_id") for r in results])  # client_id 미포함 → 무해
    items = [schemas.ReductionRunItem(**{**r, "client_name": None}) for r in results]
    return schemas.ReductionRunResponse(
        computed=out["computed"], skipped=out["skipped"], total=out["total"],
        total_reduction=out["total_reduction"], total_adjusted=out["total_adjusted"],
        items=items,
    )
