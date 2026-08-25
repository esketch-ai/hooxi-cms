"""감축 참여 레지스트리 — KISA 500대 차량 현황 원장(M3).

- POST /reduction-registry/import : KISA xlsx 업로드 → 전량 교체 적재(멱등)
- GET  /reduction-registry         : role·권역·도입구분·운수사·검색 필터 목록(페이지)
- GET  /reduction-registry/summary : role·권역별 집계 + 운수사 매칭률
차량 현황 원장(참여상태 BASELINE/PROJECT/CANDIDATE) — 감축량은 별도(project_vehicles).
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import Client, ReductionRegistry, User, get_db
from routers import common
from services import reduction_registry_import as rri
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/reduction-registry", tags=["reduction-registry"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.post("/import", response_model=schemas.ReductionRegistryImportResult)
async def import_registry(
    file: UploadFile = File(...),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """KISA 블록체인(500대) 엑셀 → 레지스트리 전량 교체 적재. KISA_IMPORT 출처만 교체(멱등)."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="빈 파일은 업로드할 수 없습니다")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기가 25MB를 초과합니다")
    try:
        rows = rri.parse_registry(content)
    except Exception as exc:  # openpyxl 파싱 실패 등
        raise HTTPException(status_code=422, detail="엑셀 파싱 실패: {0}".format(exc))
    if not rows:
        raise HTTPException(status_code=422, detail="레지스트리 시트를 찾지 못했습니다(시트명 확인)")
    result = rri.apply_registry(db, rows, replace=True)
    AuditLogger.log_action(
        db, user.user_id, "REDUCTION_REGISTRY_IMPORT", target_type="BATCH",
        new_value="created={0}, matched={1}, roles={2}".format(
            result["created"], result["client_matched"], result["by_role"]),
    )
    db.commit()
    return schemas.ReductionRegistryImportResult(
        created=result["created"],
        client_matched=result["client_matched"],
        baseline=result["by_role"].get("BASELINE", 0),
        project=result["by_role"].get("PROJECT", 0),
        candidate=result["by_role"].get("CANDIDATE", 0),
    )


@router.get("", response_model=schemas.ReductionRegistryListResponse)
def list_registry(
    role: Optional[str] = Query(None, description="BASELINE/PROJECT/CANDIDATE"),
    region: Optional[str] = Query(None),
    introduction_type: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="차량번호·업체명·차명 검색"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(ReductionRegistry)
    if role:
        q = q.filter(ReductionRegistry.role == role)
    if region:
        q = q.filter(ReductionRegistry.region == region)
    if introduction_type:
        q = q.filter(ReductionRegistry.introduction_type == introduction_type)
    if client_id:
        q = q.filter(ReductionRegistry.client_id == client_id)
    if search:
        like = "%{0}%".format(search.strip())
        q = q.filter(
            (ReductionRegistry.vehicle_no.like(like))
            | (ReductionRegistry.operator_name.like(like))
            | (ReductionRegistry.model_name.like(like))
        )
    total = q.count()
    rows = (
        q.order_by(ReductionRegistry.region, ReductionRegistry.operator_name,
                   ReductionRegistry.vehicle_no)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    cnames = common.client_name_map(db, [r.client_id for r in rows])
    items = [
        schemas.ReductionRegistryOut.model_validate(r).model_copy(
            update={"client_name": cnames.get(r.client_id)})
        for r in rows
    ]
    return schemas.ReductionRegistryListResponse(items=items, total=total)


@router.get("/summary", response_model=schemas.ReductionRegistrySummary)
def registry_summary(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """role·권역별 집계 + 운수사 매칭률 — 화면 상단 요약."""
    rows = db.query(
        ReductionRegistry.role, ReductionRegistry.region,
        ReductionRegistry.client_id,
    ).all()
    by_role = {"BASELINE": 0, "PROJECT": 0, "CANDIDATE": 0}
    by_region = {}
    matched = 0
    for role, region, client_id in rows:
        by_role[role] = by_role.get(role, 0) + 1
        rk = region or "미상"
        by_region[rk] = by_region.get(rk, 0) + 1
        if client_id:
            matched += 1
    return schemas.ReductionRegistrySummary(
        total=len(rows),
        baseline=by_role.get("BASELINE", 0),
        project=by_role.get("PROJECT", 0),
        candidate=by_role.get("CANDIDATE", 0),
        client_matched=matched,
        by_region=[{"region": k, "count": v} for k, v in sorted(by_region.items())],
    )
