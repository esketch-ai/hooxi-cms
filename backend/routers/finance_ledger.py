"""재무 원장(카본크레딧실 재무 전용, FL-1) — 사업(프로젝트) grain 조회 + 전사 총계.

전 감축사업을 사업 1행으로 나열하고, 회계 원장층 12값(부록 L.3, compute_accounting)을
그대로 표기한다. 신규 산식 없음 — 배치 회계는 finance_query(단일 진실원)에 위임한다.

총계는 사업 grain의 단순 None-안전 합이다(이중계상 구조적 불가). 비율은 합산 무의미이라
총계에서 제외하고 총이익률만 파생한다. 조회 전용(신규 컬럼 없음).

의존성은 get_current_user 하나 — 외부역할(PARTNER/INVESTOR)은 이 지점에서 자동 403(포털 격리).
FL-2에서 현재시세·재고평가를 확장한다(이번엔 회계 12값+총계만).
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user
from models import Project, ProjectSale, User, get_db
from routers import common
from services import finance_query
from services.market_rate import current_market_rate

router = APIRouter(prefix="/finance-ledger", tags=["finance-ledger"])


def _sum_opt(values):
    """None 안전 합 — 전부 None이면 None, 일부 None은 합에서 제외."""
    parts = [v for v in values if v is not None]
    return round(sum(parts), 2) if parts else None


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
    거래계약 관련 필터(buyer/hold/발행일)는 EXISTS 서브쿼리로 걸어 join 중복(사업 중복)을 막는다.
    회계는 후보 사업 전체 id로 project_accounting_batch 1회(사업당 개별 호출 금지).
    """
    q = db.query(Project)

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

    total = q.count()

    # 회계 — 필터에 걸린 사업 전체 id로 배치 1회(부분집합 아님, 총계도 이 집합 기준)
    all_pids = [r[0] for r in q.with_entities(Project.project_id).all()]
    acct_by_pid = finance_query.project_accounting_batch(db, all_pids)

    # 재고평가(비영속) — 오늘 현재시세 1회 조회(N+1 없음). 사업 상세와 동일 산식.
    rate = current_market_rate(db)
    rate_f = float(rate) if rate is not None else None

    def _inv_val(held_qty):
        """held_qty × 오늘 시세(원 단위 반올림). 시세 없거나 후시보유 없으면 None."""
        return (
            round(held_qty * rate_f)
            if rate_f is not None and held_qty and held_qty > 0
            else None
        )

    # 총계 — 필터 전체(페이지 전) 사업 grain 단순 None-안전 합. 비율은 제외, 총이익률만 파생.
    accts = list(acct_by_pid.values())
    total_sale = _sum_opt(a["sale_recognized"] for a in accts)
    total_profit = _sum_opt(a["gross_profit"] for a in accts)
    totals = schemas.FinanceLedgerTotals(
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
        inventory_valuation=_sum_opt(_inv_val(a.get("held_qty")) for a in accts),
    )

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
            **acct_by_pid.get(p.project_id, {}),
        )
        for p in rows
    ]
    return schemas.FinanceLedgerResponse(
        items=items,
        total=total,
        totals=totals,
        current_market_rate=rate_f,
    )
