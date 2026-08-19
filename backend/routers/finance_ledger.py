"""재무 원장(카본크레딧실 재무 전용, FL-1) — 사업(프로젝트) grain 조회 + 전사 총계.

전 감축사업을 사업 1행으로 나열하고, 회계 원장층 12값(부록 L.3, compute_accounting)을
그대로 표기한다. 신규 산식 없음 — 배치 회계는 finance_query(단일 진실원)에 위임한다.

총계는 사업 grain의 단순 None-안전 합이다(이중계상 구조적 불가). 비율은 합산 무의미이라
총계에서 제외하고 총이익률만 파생한다. 조회 전용(신규 컬럼 없음).

의존성은 get_current_user 하나 — 외부역할(PARTNER/INVESTOR)은 이 지점에서 자동 403(포털 격리).
FL-2에서 현재시세·재고평가를 확장한다(이번엔 회계 12값+총계만).

내보내기(EX-2): GET /finance-ledger/export는 조회보다 좁은 require_role("MANAGER") 게이트로,
목록과 동일한 _apply_filters를 써 '화면 필터=파일'을 보장한다. 행 상한·일일 반출 횟수·워터마크·
DATA_EXPORT 감사(금액 원문 미기록)로 대량 유출을 억제한다(균형 보안 5중).
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_role
from models import Project, ProjectSale, User, get_db
from routers import common
from services import finance_query
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
from services.market_rate import (
    current_market_rate,
    expected_revenue,
    trailing_avg_rate,
)

router = APIRouter(prefix="/finance-ledger", tags=["finance-ledger"])

# 내보내기 균형 보안(EX-2) — 상한/일일한도 상수·가드는 services.excel_export 공용부를 재사용한다.
# (여기로 이름을 끌어와 endpoint별 monkeypatch·가독성을 유지: DAILY_EXPORT_LIMIT·MAX_EXPORT_ROWS)


def _sum_opt(values):
    """None 안전 합 — 전부 None이면 None, 일부 None은 합에서 제외."""
    parts = [v for v in values if v is not None]
    return round(sum(parts), 2) if parts else None


def _apply_filters(
    q,
    db: Session,
    *,
    approval_status: Optional[str],
    client_id: Optional[str],
    buyer_id: Optional[str],
    is_hold: Optional[str],
    invoice_from: Optional[date],
    invoice_to: Optional[date],
    search: Optional[str],
):
    """목록·내보내기 공유 필터 적용부('필터=파일' 보장 — 단일 진실원).

    거래계약 관련 필터(buyer/hold/발행일)는 EXISTS 서브쿼리로 걸어 join 중복(사업 중복)을 막는다.
    """
    if approval_status:
        q = q.filter(Project.approval_status == approval_status)
    if client_id:
        q = q.filter(Project.client_id == client_id)
    if search and search.strip():
        kw = "%{0}%".format(common.escape_like(search.strip()))
        q = q.filter(
            Project.project_name.ilike(kw, escape="\\")
            | Project.reg_code.ilike(kw, escape="\\")
        )
    # 거래계약 조건 — EXISTS(사업 중복 금지). 다건 조건은 하나의 상관 서브쿼리로 결합.
    sale_conds = []
    if buyer_id:
        sale_conds.append(ProjectSale.buyer_id == buyer_id)
    if is_hold:
        sale_conds.append(ProjectSale.is_hold == is_hold)
    if invoice_from:
        sale_conds.append(ProjectSale.sale_invoice_date >= invoice_from)
    if invoice_to:
        sale_conds.append(ProjectSale.sale_invoice_date <= invoice_to)
    if sale_conds:
        q = q.filter(
            db.query(ProjectSale.sale_id)
            .filter(ProjectSale.project_id == Project.project_id, *sale_conds)
            .exists()
        )
    return q


def _make_inv_val(rate_f):
    """held_qty × 오늘 시세(원 단위 반올림) 클로저 — 시세 없거나 후시보유 없으면 None."""

    def _inv_val(held_qty):
        return (
            round(held_qty * rate_f)
            if rate_f is not None and held_qty and held_qty > 0
            else None
        )

    return _inv_val


def _build_totals(accts, inv_val, avg6=None):
    """필터 전체 사업 grain 단순 None-안전 합 총계 — 비율은 제외, 총이익률만 파생.

    예상수익 총계는 사업행 leaf(Σeff × 6개월평균시세)의 None-안전 합 — 사업행==총계 정합.
    """
    total_sale = _sum_opt(a["sale_recognized"] for a in accts)
    total_profit = _sum_opt(a["gross_profit"] for a in accts)
    total_expected_revenue = _sum_opt(
        expected_revenue(a.get("effective_reduction_sum"), avg6) for a in accts
    )
    return schemas.FinanceLedgerTotals(
        product=_sum_opt(a["product"] for a in accts),
        expected_payment=_sum_opt(a["expected_payment"] for a in accts),
        wip1=_sum_opt(a["wip1"] for a in accts),
        wip2=_sum_opt(a["wip2"] for a in accts),
        liability=_sum_opt(a["liability"] for a in accts),
        inventory=_sum_opt(a["inventory"] for a in accts),
        sale_recognized=total_sale,
        gross_profit=total_profit,
        profit_rate=(
            round(total_profit / total_sale, 3)
            if total_profit is not None and total_sale
            else None
        ),
        held_qty=(
            round(sum(a.get("held_qty", 0.0) or 0.0 for a in accts), 3)
            if accts
            else None
        ),
        inventory_valuation=_sum_opt(inv_val(a.get("held_qty")) for a in accts),
        expected_revenue=total_expected_revenue,
    )


@router.get("", response_model=schemas.FinanceLedgerResponse)
def list_finance_ledger(
    approval_status: Optional[str] = Query(None, description="승인상태 필터(Project)"),
    client_id: Optional[str] = Query(None, description="대표 고객사 필터(Project.client_id)"),
    buyer_id: Optional[str] = Query(None, description="매수자 필터(거래계약 보유 사업)"),
    is_hold: Optional[str] = Query(None, description="후시보유 계약 보유 사업(Y)"),
    invoice_from: Optional[date] = Query(None, description="매출세금계산서 발행일 시작(이상)"),
    invoice_to: Optional[date] = Query(None, description="매출세금계산서 발행일 끝(이하)"),
    search: Optional[str] = Query(None, description="사업명·사업번호 검색"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """재무 원장 — 사업 grain 1행 목록(필터·검색·페이지) + 필터 전체 총계.

    후보 사업은 tb_project 전체를 base로 필터를 적용해 distinct 집합으로 확정한다.
    회계는 후보 사업 전체 id로 project_accounting_batch 1회(사업당 개별 호출 금지).
    """
    q = _apply_filters(
        db.query(Project),
        db,
        approval_status=approval_status,
        client_id=client_id,
        buyer_id=buyer_id,
        is_hold=is_hold,
        invoice_from=invoice_from,
        invoice_to=invoice_to,
        search=search,
    )

    total = q.count()

    # 회계 — 필터에 걸린 사업 전체 id로 배치 1회(부분집합 아님, 총계도 이 집합 기준)
    all_pids = [r[0] for r in q.with_entities(Project.project_id).all()]
    acct_by_pid = finance_query.project_accounting_batch(db, all_pids)

    # 재고평가(비영속) — 오늘 현재시세 1회 조회(N+1 없음). 사업 상세와 동일 산식.
    rate = current_market_rate(db)
    rate_f = float(rate) if rate is not None else None
    _inv_val = _make_inv_val(rate_f)

    # 예상수익 — 직전 6개월 평균시세 1회 산출(단일 소스). 사업행 leaf에서 Σeff×avg6 절사.
    avg6 = trailing_avg_rate(db)

    # 총계 — 필터 전체(페이지 전) 사업 grain 단순 None-안전 합. 비율은 제외, 총이익률만 파생.
    totals = _build_totals(list(acct_by_pid.values()), _inv_val, avg6)

    # items — page 슬라이스(정렬: 승인일 desc, project_id asc 타이브레이크)
    rows = (
        q.order_by(Project.approved_at.desc(), Project.project_id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        schemas.FinanceLedgerRow(
            project_id=p.project_id,
            project_name=p.project_name,
            reg_code=p.reg_code,
            approval_status=p.approval_status,
            approved_at=p.approved_at,
            inventory_valuation=_inv_val(
                acct_by_pid.get(p.project_id, {}).get("held_qty")
            ),
            expected_revenue=expected_revenue(
                acct_by_pid.get(p.project_id, {}).get("effective_reduction_sum"), avg6
            ),
            **acct_by_pid.get(p.project_id, {}),
        )
        for p in rows
    ]
    return schemas.FinanceLedgerResponse(
        items=items,
        total=total,
        totals=totals,
        current_market_rate=rate_f,
        market_rate_avg6=float(avg6) if avg6 is not None else None,
    )


# 내보내기 컬럼 규격(화면 컬럼과 정합) — 사업번호·사업명·승인상태 + 회계 원장층 값
_EXPORT_COLUMNS = [
    ColumnSpec("reg_code", "사업번호", "text"),
    ColumnSpec("project_name", "사업명", "text"),
    ColumnSpec("approval_status", "승인상태", "text"),
    ColumnSpec("product", "제품(원가)", "money"),
    ColumnSpec("expected_payment", "예상지급액", "money"),
    ColumnSpec("wip1", "미착품1", "money"),
    ColumnSpec("wip2", "미착품2", "money"),
    ColumnSpec("liability", "지급채무", "money"),
    ColumnSpec("inventory", "재고자산", "money"),
    ColumnSpec("payout_rate", "지급률", "percent"),
    ColumnSpec("sale_recognized", "매출인식", "money"),
    ColumnSpec("gross_profit", "매출이익", "money"),
    ColumnSpec("profit_rate", "매출이익률", "percent"),
    ColumnSpec("held_qty", "후시보유량", "number"),
    ColumnSpec("inventory_valuation", "재고평가", "money"),
    ColumnSpec("expected_revenue", "예상수익", "money"),
]


def _export_filter_summary(
    n,
    approval_status,
    client_id,
    buyer_id,
    is_hold,
    invoice_from,
    invoice_to,
    search,
):
    """감사 new_value — 행수 + 필터 요약(id·상태·기간)만. 금액·비밀값 원문 미기록(R2-E6)."""
    parts = []
    if approval_status:
        parts.append("approval={0}".format(approval_status))
    if client_id:
        parts.append("client={0}".format(client_id))
    if buyer_id:
        parts.append("buyer={0}".format(buyer_id))
    if is_hold:
        parts.append("hold={0}".format(is_hold))
    if invoice_from:
        parts.append("from={0}".format(invoice_from))
    if invoice_to:
        parts.append("to={0}".format(invoice_to))
    if search and search.strip():
        parts.append("search={0}".format(search.strip()))
    return "rows={0}; filters={1}".format(n, ", ".join(parts) if parts else "none")


@router.get("/export")
def export_finance_ledger(
    approval_status: Optional[str] = Query(None, description="승인상태 필터(Project)"),
    client_id: Optional[str] = Query(None, description="대표 고객사 필터(Project.client_id)"),
    buyer_id: Optional[str] = Query(None, description="매수자 필터(거래계약 보유 사업)"),
    is_hold: Optional[str] = Query(None, description="후시보유 계약 보유 사업(Y)"),
    invoice_from: Optional[date] = Query(None, description="매출세금계산서 발행일 시작(이상)"),
    invoice_to: Optional[date] = Query(None, description="매출세금계산서 발행일 끝(이하)"),
    search: Optional[str] = Query(None, description="사업명·사업번호 검색"),
    user: User = Depends(require_role("MANAGER")),
    db: Session = Depends(get_db),
):
    """재무 원장 엑셀 내보내기(EX-2) — 화면과 동일 필터의 '전체' 결과를 .xlsx로.

    조회(목록)보다 좁은 MANAGER 게이트 + 행 상한(400)·일일 반출 횟수(429)·워터마크·
    DATA_EXPORT 감사(금액 원문 미기록)로 대량 유출을 억제한다. 페이지네이션 없음(전체).
    """
    # 일일 반출 횟수 제한 — 공용 가드(오늘 KST DATA_EXPORT 감사 건수 재사용)
    check_export_quota(db, user, daily_limit=DAILY_EXPORT_LIMIT)

    q = _apply_filters(
        db.query(Project),
        db,
        approval_status=approval_status,
        client_id=client_id,
        buyer_id=buyer_id,
        is_hold=is_hold,
        invoice_from=invoice_from,
        invoice_to=invoice_to,
        search=search,
    )

    total = q.count()
    # 행 상한 — 공용 가드(무음 잘라내기 금지, 초과 시 400)
    enforce_row_limit(total, max_rows=MAX_EXPORT_ROWS)

    all_pids = [r[0] for r in q.with_entities(Project.project_id).all()]
    acct_by_pid = finance_query.project_accounting_batch(db, all_pids)

    rate = current_market_rate(db)
    rate_f = float(rate) if rate is not None else None
    _inv_val = _make_inv_val(rate_f)

    avg6 = trailing_avg_rate(db)

    totals = _build_totals(list(acct_by_pid.values()), _inv_val, avg6)

    # 전체 사업 행(목록과 동일 정렬, 페이지네이션 없음)
    projects = q.order_by(
        Project.approved_at.desc(), Project.project_id.asc()
    ).all()
    rows = []
    for p in projects:
        acct = acct_by_pid.get(p.project_id, {})
        row = {
            "reg_code": p.reg_code,
            "project_name": p.project_name,
            "approval_status": p.approval_status,
            "inventory_valuation": _inv_val(acct.get("held_qty")),
            "expected_revenue": expected_revenue(
                acct.get("effective_reduction_sum"), avg6
            ),
        }
        row.update(acct)
        rows.append(row)

    # 합계행 = totals(화면 총계와 동일 원천)
    total_row = totals.model_dump()

    content = build_workbook(
        _EXPORT_COLUMNS,
        rows,
        sheet_title="재무원장",
        watermark=build_watermark(user),
        total_row=total_row,
    )

    # 감사 — 반환 직전 기록(행수·필터 요약만, 금액·비밀값 원문 미기록) 후 커밋
    AuditLogger.log_action(
        db,
        user.user_id,
        "DATA_EXPORT",
        target_type="FINANCE_LEDGER",
        new_value=_export_filter_summary(
            len(rows),
            approval_status,
            client_id,
            buyer_id,
            is_hold,
            invoice_from,
            invoice_to,
            search,
        ),
    )
    db.commit()

    return xlsx_response(content, export_filename("재무원장"))
