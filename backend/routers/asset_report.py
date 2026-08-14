"""자산관리 보고(P2) — 운수사×사업 정산 요약 매트릭스 조회 + 엑셀 내보내기.

운수사별 예상지급액·감축량 요약과 사업별 드릴다운을 제공한다(매출/매입 제외 — 운수사
귀속 애매, 예상지급액 중심). 집계는 services.settlement_summary(단일 진실원)에 위임한다
(재계산 없음). 정산 확정/지급 상태는 P4 의존 → 이번엔 '예상지급액(정산예정)'만.

조회 의존성은 get_current_user 하나 — OBSERVER(경영전략실)는 정확매칭 화이트리스트
(/settlement-summary)로 통과, 외부역할(PARTNER/INVESTOR)은 원천 403(포털 격리).
내보내기(export)는 조회보다 좁은 require_role("MANAGER") 게이트 + 행 상한(400)·일일
반출 횟수(429)·워터마크·DATA_EXPORT 감사(금액 원문 미기록, R2-E6)로 대량 유출을 억제한다.
export 경로는 화이트리스트 미포함 → OBSERVER 자연 차단.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_role
from models import User, get_db
from services import settlement_summary as summary_service
from services.audit_logger import AuditLogger
from services.excel_export import (
    DAILY_EXPORT_LIMIT,
    MAX_EXPORT_ROWS,
    ColumnSpec,
    build_watermark,
    build_workbook,
    check_export_quota,
    enforce_row_limit,
    export_filename,
    xlsx_response,
)

router = APIRouter(prefix="/asset-report", tags=["asset-report"])

# 내보내기 균형 보안(EX-2) — 상한/일일한도 상수·가드는 services.excel_export 공용부를 재사용한다.
# (여기로 이름을 끌어와 endpoint별 monkeypatch·가독성을 유지: DAILY_EXPORT_LIMIT·MAX_EXPORT_ROWS)


@router.get("/settlement-summary", response_model=schemas.SettlementSummaryResponse)
def get_settlement_summary(
    client_id: Optional[str] = Query(None, description="운수사 필터(ProjectVehicle.client_id)"),
    client_type: Optional[str] = Query(None, description="고객사 구분 필터(Client.client_type)"),
    region: Optional[str] = Query(None, description="지역 필터(Client.region)"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """운수사×사업 정산 요약 매트릭스 — 운수사별 롤업 + 사업 드릴다운 + 전사 총계."""
    return summary_service.settlement_summary(
        db, client_id=client_id, client_type=client_type, region=region
    )


# 내보내기 컬럼 규격(화면 컬럼과 정합) — 운수사×사업 평탄화 1행
_EXPORT_COLUMNS = [
    ColumnSpec("company_name", "운수사", "text"),
    ColumnSpec("project_name", "사업명", "text"),
    ColumnSpec("vehicle_count", "차량수", "number"),
    ColumnSpec("total_reduction", "총감축량", "number"),
    ColumnSpec("effective_reduction", "잔여반영감축량", "number"),
    ColumnSpec("expected_payout", "예상지급액", "money"),
]


def _export_filter_summary(n, client_id, client_type, region):
    """감사 new_value — 행수 + 필터 요약(id·구분·지역)만. 금액·비밀값 원문 미기록(R2-E6)."""
    parts = []
    if client_id:
        parts.append("client={0}".format(client_id))
    if client_type:
        parts.append("type={0}".format(client_type))
    if region:
        parts.append("region={0}".format(region))
    return "rows={0}; filters={1}".format(n, ", ".join(parts) if parts else "none")


@router.get("/settlement-summary/export")
def export_settlement_summary(
    client_id: Optional[str] = Query(None, description="운수사 필터(ProjectVehicle.client_id)"),
    client_type: Optional[str] = Query(None, description="고객사 구분 필터(Client.client_type)"),
    region: Optional[str] = Query(None, description="지역 필터(Client.region)"),
    user: User = Depends(require_role("MANAGER")),
    db: Session = Depends(get_db),
):
    """정산 요약 엑셀 내보내기(EX-2) — 화면과 동일 필터의 운수사×사업 평탄화 전체 결과를 .xlsx로.

    조회(요약)보다 좁은 MANAGER 게이트 + 행 상한(400)·일일 반출 횟수(429)·워터마크·
    DATA_EXPORT 감사(금액 원문 미기록)로 대량 유출을 억제한다. 페이지네이션 없음(전체).
    """
    # 일일 반출 횟수 제한 — 공용 가드(오늘 KST DATA_EXPORT 감사 건수 재사용)
    check_export_quota(db, user, daily_limit=DAILY_EXPORT_LIMIT)

    data = summary_service.settlement_summary(
        db, client_id=client_id, client_type=client_type, region=region
    )

    # 운수사×사업 평탄화 — 운수사-사업 1행(화면 드릴다운을 펼침)
    rows = []
    for item in data["items"]:
        for p in item["projects"]:
            rows.append(
                {
                    "company_name": item["company_name"],
                    "project_name": p["project_name"],
                    "vehicle_count": p["vehicle_count"],
                    "total_reduction": p["total_reduction"],
                    "effective_reduction": p["effective_reduction"],
                    "expected_payout": p["expected_payout"],
                }
            )

    # 행 상한 — 공용 가드(무음 잘라내기 금지, 초과 시 400)
    enforce_row_limit(len(rows), max_rows=MAX_EXPORT_ROWS)

    # 합계행 = totals(화면 총계와 동일 원천)
    totals = data["totals"]
    total_row = {
        "vehicle_count": totals["participating_vehicle_count"],
        "total_reduction": totals["total_reduction"],
        "effective_reduction": totals["effective_reduction"],
        "expected_payout": totals["expected_payout"],
    }

    content = build_workbook(
        _EXPORT_COLUMNS,
        rows,
        sheet_title="자산관리보고",
        watermark=build_watermark(user),
        total_row=total_row,
    )

    # 감사 — 반환 직전 기록(행수·필터 요약만, 금액·비밀값 원문 미기록) 후 커밋
    AuditLogger.log_action(
        db,
        user.user_id,
        "DATA_EXPORT",
        target_type="ASSET_REPORT",
        new_value=_export_filter_summary(len(rows), client_id, client_type, region),
    )
    db.commit()

    return xlsx_response(content, export_filename("자산관리보고"))
