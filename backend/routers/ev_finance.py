"""전기버스 도입 재무(민간투자비율 근거) — 차량가액·보조금·자부담금 원장(D2).

- POST /ev-finance/import : 증빙 03 엑셀 업로드 → 전량 교체 적재(멱등)
- GET  /ev-finance         : 권역·운수사·검색 필터 목록(페이지)
- GET  /ev-finance/summary : 대수·투자 총액·보조금 총액·평균 민간비율
민간비율 근거를 구성으로 관리(감사가능성). 조회 내부 인증, 적재 master.write.
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import EvFinance, User, get_db
from routers import common
from services import ev_finance_import as efi
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/ev-finance", tags=["ev-finance"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.post("/import", response_model=schemas.EvFinanceImportResult)
async def import_ev_finance(
    file: UploadFile = File(...),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """차량별 차량가액·보조금·자부담금 엑셀 → 전량 교체 적재(EVIDENCE_IMPORT 출처, 멱등)."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="빈 파일은 업로드할 수 없습니다")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기가 25MB를 초과합니다")
    try:
        rows = efi.parse_ev_finance(content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="엑셀 파싱 실패: {0}".format(exc))
    if not rows:
        raise HTTPException(status_code=422, detail="재무 시트를 찾지 못했습니다(헤더 확인)")
    result = efi.apply_ev_finance(db, rows, replace=True)
    AuditLogger.log_action(
        db, user.user_id, "EV_FINANCE_IMPORT", target_type="BATCH",
        new_value="created={0}, matched={1}".format(result["created"], result["client_matched"]),
    )
    db.commit()
    return schemas.EvFinanceImportResult(**result)


@router.get("", response_model=schemas.EvFinanceListResponse)
def list_ev_finance(
    region: Optional[str] = Query(None),
    client_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="차량번호·운수사 검색"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(EvFinance)
    if region:
        q = q.filter(EvFinance.region == region)
    if client_id:
        q = q.filter(EvFinance.client_id == client_id)
    if search:
        like = "%{0}%".format(search.strip())
        q = q.filter((EvFinance.vehicle_no.like(like)) | (EvFinance.operator_name.like(like)))
    total = q.count()
    rows = (
        q.order_by(EvFinance.region, EvFinance.operator_name, EvFinance.vehicle_no)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    cnames = common.client_name_map(db, [r.client_id for r in rows])
    items = [
        schemas.EvFinanceOut.model_validate(r).model_copy(
            update={"client_name": cnames.get(r.client_id)})
        for r in rows
    ]
    return schemas.EvFinanceListResponse(items=items, total=total)


@router.get("/summary", response_model=schemas.EvFinanceSummary)
def ev_finance_summary(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """대수·차량가액 총액·보조금 총액·자부담 총액·평균 민간비율."""
    rows = db.query(
        EvFinance.vehicle_value, EvFinance.low_floor_subsidy, EvFinance.ev_subsidy,
        EvFinance.self_payment, EvFinance.private_ratio,
    ).all()
    n = len(rows)
    value_sum = sum(float(r[0] or 0) for r in rows)
    subsidy_sum = sum(float(r[1] or 0) + float(r[2] or 0) for r in rows)
    self_sum = sum(float(r[3] or 0) for r in rows)
    ratios = [float(r[4]) for r in rows if r[4] is not None]
    avg_ratio = round(sum(ratios) / len(ratios), 4) if ratios else 0.0
    return schemas.EvFinanceSummary(
        count=n,
        vehicle_value_total=round(value_sum, 2),
        subsidy_total=round(subsidy_sum, 2),
        self_payment_total=round(self_sum, 2),
        avg_private_ratio=avg_ratio,
    )
