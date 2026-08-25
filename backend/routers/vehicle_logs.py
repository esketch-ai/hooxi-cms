"""차량 월별 운행·충전 원천 로그(D6, P1·P2).

- POST /vehicle-logs/import      : 취합본 WIDE 엑셀 → 월별 로그 upsert(차량·월·출처)
- GET  /vehicle-logs/consolidate : 로그 → 차량×월 통합 표(자동 정리 뷰)
- POST /vehicle-logs/aggregate   : 기간 Σ → 연평균 project → (옵션)VehicleCalcInput 갱신
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import User, get_db
from services import etas_raw_import as eri
from services import vehicle_log_aggregate as agg
from services import vehicle_log_import as vli
from services.audit_logger import AuditLogger

router = APIRouter(tags=["vehicle-logs"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.post("/vehicle-logs/import", response_model=schemas.VehicleLogImportResult)
async def import_vehicle_logs(
    file: UploadFile = File(...),
    batch: Optional[str] = Query(None, description="업로드 배치 표기"),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """취합본 WIDE(YYYY년MM월_운행일수/운행거리/충전량) → 월별 로그로 분해 upsert."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="빈 파일은 업로드할 수 없습니다")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기가 25MB를 초과합니다")
    try:
        rows = vli.parse_integrated_wide(content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="엑셀 파싱 실패: {0}".format(exc))
    if not rows:
        raise HTTPException(
            status_code=422,
            detail="차량번호 또는 'YYYY년MM월_지표' 헤더를 찾지 못했습니다")
    result = vli.apply_logs(db, rows, batch=batch)
    AuditLogger.log_action(
        db, user.user_id, "VEHICLE_LOG_IMPORT", target_type="BATCH",
        new_value="created={0}, updated={1}, vehicles={2}".format(
            result["created"], result["updated"], result["vehicles"]),
    )
    db.commit()
    return schemas.VehicleLogImportResult(**result)


@router.post("/vehicle-logs/import-raw", response_model=schemas.VehicleLogRawImportResult)
async def import_raw_vehicle_logs(
    files: List[UploadFile] = File(...),
    batch: Optional[str] = Query(None, description="업로드 배치 표기"),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """운수사별 원본 다건 업로드(eTAS .xls / BMS취합 .xlsx) → 구조 자동판별 후 로그 upsert."""
    if not files:
        raise HTTPException(status_code=422, detail="업로드할 파일이 없습니다")
    all_rows: list = []
    parsed = 0
    skipped: list = []
    for f in files:
        content = await f.read()
        if not content or len(content) > MAX_UPLOAD_BYTES:
            skipped.append(f.filename or "(무명)")
            continue
        try:
            rows = eri.parse_raw_file(content, f.filename or "")
        except Exception:
            skipped.append(f.filename or "(무명)")
            continue
        if rows:
            all_rows.extend(rows)
            parsed += 1
        else:
            skipped.append(f.filename or "(무명)")
    if not all_rows:
        raise HTTPException(
            status_code=422,
            detail="파싱 가능한 데이터가 없습니다(eTAS .xls 또는 BMS취합 .xlsx 확인)")
    result = vli.apply_logs(db, all_rows, batch=batch)
    AuditLogger.log_action(
        db, user.user_id, "VEHICLE_LOG_RAW_IMPORT", target_type="BATCH",
        new_value="files={0}/{1}, created={2}, updated={3}".format(
            parsed, len(files), result["created"], result["updated"]),
    )
    db.commit()
    return schemas.VehicleLogRawImportResult(
        files=len(files), parsed_files=parsed, skipped_files=skipped, **result)


@router.get("/vehicle-logs/consolidate", response_model=schemas.VehicleLogConsolidateResponse)
def consolidate_vehicle_logs(
    region: Optional[str] = Query(None),
    ym_from: Optional[str] = Query(None, description="YYYY-MM"),
    ym_to: Optional[str] = Query(None, description="YYYY-MM"),
    program_only: bool = Query(False, description="레지스트리 프로그램 차량만"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    out = agg.consolidate(db, region=region, ym_from=ym_from, ym_to=ym_to,
                          program_only=program_only)
    return schemas.VehicleLogConsolidateResponse(**out)


@router.post("/vehicle-logs/aggregate", response_model=schemas.VehicleLogAggregateResponse)
def aggregate_vehicle_logs(
    region: Optional[str] = Query(None),
    ym_from: Optional[str] = Query(None, description="YYYY-MM"),
    ym_to: Optional[str] = Query(None, description="YYYY-MM"),
    commit_project: bool = Query(False, description="산정 입력 사업(project) 측 갱신"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """기간 Σ → 연평균 project. commit_project면 VehicleCalcInput 갱신(master.write 필요)."""
    if commit_project:
        require_permission("master.write")(user)
    out = agg.aggregate_to_calc(db, region=region, ym_from=ym_from, ym_to=ym_to,
                                commit_project=commit_project)
    if commit_project:
        AuditLogger.log_action(
            db, user.user_id, "VEHICLE_LOG_AGGREGATE", target_type="BATCH",
            new_value="updated={0}, aggregated={1}".format(out["updated"], out["aggregated"]),
        )
        db.commit()
    items = [schemas.VehicleLogAggregateItem(**r) for r in out.pop("results")]
    return schemas.VehicleLogAggregateResponse(items=items, **out)
