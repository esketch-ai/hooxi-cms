"""세금계산서 원장 — 홈택스 보안메일 HTML 자동반영 (P5).

- POST /tax-invoices/preview : HTML 다건 업로드 → 파싱·매칭·중복 미리보기(DB 무변경)
- POST /tax-invoices/commit  : HTML 다건 → 원장(tb_tax_invoice) 적재(승인번호 멱등)
- GET  /tax-invoices         : 원장 조회(방향/기간/검색 필터, 페이지)
- DELETE /tax-invoices/{id}  : 원장 항목 삭제(정정용)

복호화·파싱·매칭은 services.tax_invoice / tax_invoice_import. 감사 로그엔 건수·승인번호만
남기고 사업자번호·금액 원문은 남기지 않는다(R2-E6 취지).
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import Project, TaxInvoice, User, get_db
from services import dropbox_storage, tax_invoice_import
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

router = APIRouter(prefix="/tax-invoices", tags=["tax-invoices"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # HTML 1건 상한(documents와 동일 기준)


async def _read_html_files(files: List[UploadFile]) -> List[tuple]:
    """업로드 파일들을 (filename, html_text) 목록으로. 25MB 초과는 413."""
    out = []
    for f in files:
        content = await f.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="파일 크기가 25MB를 초과합니다: {0}".format(f.filename))
        out.append((f.filename, content.decode("utf-8", errors="replace")))
    return out


# 정합성 이슈 필터 — 미연결(사업 미귀속)·미매칭(상대 마스터 없음)·음수(수정취소)
def _apply_issue_filter(query, issue: Optional[str]):
    if issue == "unlinked":  # 사업(project) 미연결
        return query.filter(TaxInvoice.project_id.is_(None))
    if issue == "unmatched":  # 상대(운수사/투자사) 마스터 미매칭
        return query.filter(
            TaxInvoice.matched_client_id.is_(None) & TaxInvoice.matched_buyer_id.is_(None)
        )
    if issue == "negative":  # 수정취소 등 음수 공급가액
        return query.filter(TaxInvoice.supply_amount < 0)
    return query


@router.get("", response_model=schemas.TaxInvoiceListResponse)
def list_tax_invoices(
    direction: Optional[str] = Query(None, description="매입/매출/미상"),
    search: Optional[str] = Query(None, description="상대 사업자번호·상호 부분검색"),
    issue: Optional[str] = Query(None, description="정합성: unlinked/unmatched/negative"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(TaxInvoice)
    if direction:
        query = query.filter(TaxInvoice.direction == direction)
    if date_from:
        query = query.filter(TaxInvoice.issue_date >= date_from)
    if date_to:
        query = query.filter(TaxInvoice.issue_date <= date_to)
    if search:
        like = "%{0}%".format(search.strip())
        query = query.filter(
            (TaxInvoice.counterpart_reg_no.like(like))
            | (TaxInvoice.counterpart_name.like(like))
            | (TaxInvoice.invoicer_name.like(like))
            | (TaxInvoice.invoicee_name.like(like))
        )
    query = _apply_issue_filter(query, issue)
    total = query.count()
    rows = (
        query.order_by(TaxInvoice.issue_date.desc(), TaxInvoice.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.TaxInvoiceListResponse(
        items=[schemas.TaxInvoiceOut.model_validate(r) for r in rows], total=total
    )


@router.get("/summary", response_model=schemas.TaxInvoiceSummary)
def tax_invoice_summary(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """세금계산서 요약(경영전략실) — 기간 내 매입·매출·순액·부가세 + 월별 추이.

    원장(tb_tax_invoice) 단일 원천에서 파생(별도 저장 없음). 월 그룹핑은 방언 무관하게
    파이썬에서 처리한다(경영 관찰과 동일 관용구). 공급가액(부가세 제외)이 순액 기준.
    """
    q = db.query(
        TaxInvoice.issue_date,
        TaxInvoice.direction,
        TaxInvoice.supply_amount,
        TaxInvoice.tax_amount,
    )
    if date_from:
        q = q.filter(TaxInvoice.issue_date >= date_from)
    if date_to:
        q = q.filter(TaxInvoice.issue_date <= date_to)

    ps = ss = pt = st = 0.0
    pc = sc = 0
    monthly = {}  # 'YYYY-MM' -> [purchase, sales]
    for issue_date, direction, supply, tax in q.all():
        supply = float(supply or 0)
        tax = float(tax or 0)
        if direction == "매입":
            ps += supply
            pt += tax
            pc += 1
        elif direction == "매출":
            ss += supply
            st += tax
            sc += 1
        if issue_date:
            mk = "{0:04d}-{1:02d}".format(issue_date.year, issue_date.month)
            m = monthly.setdefault(mk, [0.0, 0.0])
            if direction == "매입":
                m[0] += supply
            elif direction == "매출":
                m[1] += supply

    months = [
        schemas.TaxInvoiceMonthPoint(
            month=k, purchase=round(v[0], 2), sales=round(v[1], 2), net=round(v[1] - v[0], 2)
        )
        for k, v in sorted(monthly.items())
    ]
    return schemas.TaxInvoiceSummary(
        purchase_supply=round(ps, 2),
        sales_supply=round(ss, 2),
        net_supply=round(ss - ps, 2),
        purchase_tax=round(pt, 2),
        sales_tax=round(st, 2),
        purchase_count=pc,
        sales_count=sc,
        months=months,
    )


@router.get("/issue-counts", response_model=schemas.TaxInvoiceIssueCounts)
def tax_invoice_issue_counts(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """정합성 워크리스트 카운트 — 미연결(사업)·미매칭(거래처)·음수(수정취소). 기간 필터 반영."""
    def _base():
        q = db.query(TaxInvoice)
        if date_from:
            q = q.filter(TaxInvoice.issue_date >= date_from)
        if date_to:
            q = q.filter(TaxInvoice.issue_date <= date_to)
        return q

    return schemas.TaxInvoiceIssueCounts(
        unlinked=_apply_issue_filter(_base(), "unlinked").count(),
        unmatched=_apply_issue_filter(_base(), "unmatched").count(),
        negative=_apply_issue_filter(_base(), "negative").count(),
    )


_BREAKDOWN_AXES = ("counterpart", "project", "entity")


@router.get("/breakdown", response_model=schemas.TaxInvoiceBreakdown)
def tax_invoice_breakdown(
    axis: str = Query("counterpart", description="counterpart/project/entity"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """축별 집계 — 거래처별/사업별/자사법인별 매입·매출·순액·건수(공급가액 기준).

    자사법인 축은 방향으로 자사 측을 정한다(매입=받는자, 매출=공급자). 사업 축의
    미연결(project_id NULL)은 '미연결'로 묶는다. 상위 limit건(총 거래량 순).
    """
    if axis not in _BREAKDOWN_AXES:
        raise HTTPException(status_code=422, detail="axis는 counterpart/project/entity 중 하나여야 합니다")
    q = db.query(
        TaxInvoice.direction, TaxInvoice.supply_amount,
        TaxInvoice.counterpart_reg_no, TaxInvoice.counterpart_name,
        TaxInvoice.project_id,
        TaxInvoice.invoicer_reg_no, TaxInvoice.invoicer_name,
        TaxInvoice.invoicee_reg_no, TaxInvoice.invoicee_name,
    )
    if date_from:
        q = q.filter(TaxInvoice.issue_date >= date_from)
    if date_to:
        q = q.filter(TaxInvoice.issue_date <= date_to)

    groups = {}
    for r in q.all():
        if axis == "counterpart":
            key = r.counterpart_reg_no or r.counterpart_name or "미상"
            label = r.counterpart_name or r.counterpart_reg_no or "미상"
        elif axis == "project":
            key = r.project_id or "__none__"
            label = None  # 나중에 사업명 해석
        else:  # entity — 자사 측(방향 기준)
            if r.direction == "매입":
                key = r.invoicee_reg_no or "미상"
                label = r.invoicee_name or key
            elif r.direction == "매출":
                key = r.invoicer_reg_no or "미상"
                label = r.invoicer_name or key
            else:
                key = "미상"
                label = "미상"
        g = groups.setdefault(key, {"label": label, "purchase": 0.0, "sales": 0.0, "count": 0})
        supply = float(r.supply_amount or 0)
        if r.direction == "매입":
            g["purchase"] += supply
        elif r.direction == "매출":
            g["sales"] += supply
        g["count"] += 1

    if axis == "project":
        ids = [k for k in groups if k != "__none__"]
        names = dict(
            db.query(Project.project_id, Project.project_name)
            .filter(Project.project_id.in_(ids)).all()
        ) if ids else {}
        for k, g in groups.items():
            g["label"] = "미연결" if k == "__none__" else (names.get(k) or k)

    rows = [
        schemas.TaxInvoiceBreakdownRow(
            key=k, label=g["label"] or k,
            purchase=round(g["purchase"], 2), sales=round(g["sales"], 2),
            net=round(g["sales"] - g["purchase"], 2), count=g["count"],
        )
        for k, g in groups.items()
    ]
    rows.sort(key=lambda x: abs(x.purchase) + abs(x.sales), reverse=True)
    return schemas.TaxInvoiceBreakdown(axis=axis, rows=rows[:limit])


_EXPORT_COLUMNS = [
    ColumnSpec("issue_date", "작성일", "date"),
    ColumnSpec("direction", "방향", "text"),
    ColumnSpec("invoicer", "공급자", "text"),
    ColumnSpec("invoicee", "받는자", "text"),
    ColumnSpec("counterpart", "상대", "text"),
    ColumnSpec("supply", "공급가액", "money"),
    ColumnSpec("tax", "세액", "money"),
    ColumnSpec("total", "합계", "money"),
    ColumnSpec("approval_no", "승인번호", "text"),
    ColumnSpec("linked", "사업연결", "text"),
    ColumnSpec("matched", "거래처매칭", "text"),
]


@router.get("/export")
def export_tax_invoices(
    direction: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    issue: Optional[str] = Query(None),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """세금계산서 원장 엑셀 내보내기(경영전략실) — 현재 필터 결과 전체.

    행상한(무음 잘라내기 금지)·일일 반출 횟수·워터마크·DATA_EXPORT 감사(공용 관용구).
    """
    check_export_quota(db, user, daily_limit=DAILY_EXPORT_LIMIT)
    query = db.query(TaxInvoice)
    if direction:
        query = query.filter(TaxInvoice.direction == direction)
    if date_from:
        query = query.filter(TaxInvoice.issue_date >= date_from)
    if date_to:
        query = query.filter(TaxInvoice.issue_date <= date_to)
    if search:
        like = "%{0}%".format(search.strip())
        query = query.filter(
            (TaxInvoice.counterpart_reg_no.like(like))
            | (TaxInvoice.counterpart_name.like(like))
            | (TaxInvoice.invoicer_name.like(like))
            | (TaxInvoice.invoicee_name.like(like))
        )
    query = _apply_issue_filter(query, issue)
    total = query.count()
    enforce_row_limit(total, max_rows=MAX_EXPORT_ROWS)
    logs = query.order_by(TaxInvoice.issue_date.desc(), TaxInvoice.created_at.desc()).all()
    rows = [
        {
            "issue_date": r.issue_date,
            "direction": r.direction,
            "invoicer": r.invoicer_name or r.invoicer_reg_no,
            "invoicee": r.invoicee_name or r.invoicee_reg_no,
            "counterpart": r.counterpart_name or r.counterpart_reg_no,
            "supply": float(r.supply_amount) if r.supply_amount is not None else None,
            "tax": float(r.tax_amount) if r.tax_amount is not None else None,
            "total": float(r.total_amount) if r.total_amount is not None else None,
            "approval_no": r.approval_no,
            "linked": "연결" if r.project_id else "미연결",
            "matched": "매칭" if (r.matched_client_id or r.matched_buyer_id) else "미매칭",
        }
        for r in logs
    ]
    content = build_workbook(
        _EXPORT_COLUMNS, rows, sheet_title="세금계산서",
        watermark=build_watermark(user), total_row=None,
    )
    AuditLogger.log_action(
        db, user.user_id, "DATA_EXPORT", target_type="TAX_INVOICE",
        new_value="rows={0}; direction={1}; issue={2}; from={3}; to={4}".format(
            total, direction or "-", issue or "-", date_from or "-", date_to or "-"),
    )
    db.commit()
    return xlsx_response(content, export_filename("세금계산서"))


@router.post("/preview", response_model=schemas.TaxInvoicePreviewResponse)
async def preview_tax_invoices(
    files: List[UploadFile] = File(...),
    _: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """HTML 다건 미리보기 — 파싱·매칭·중복 판정만(DB 무변경)."""
    parsed_files = await _read_html_files(files)
    items = tax_invoice_import.analyze_files(db, parsed_files)
    return schemas.TaxInvoicePreviewResponse(items=items)


@router.post("/commit", response_model=schemas.TaxInvoiceCommitResponse)
async def commit_tax_invoices(
    files: List[UploadFile] = File(...),
    project_id: Optional[str] = Query(None, description="(선택) 프로젝트 연결"),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """HTML 다건 적용 — 원장 적재(승인번호 멱등, 중복 스킵). 건별 격리."""
    parsed_files = await _read_html_files(files)
    result = tax_invoice_import.commit_files(
        db, parsed_files, actor_id=user.user_id, project_id=(project_id or None)
    )
    # 감사 — 건수 요약만(승인번호·금액 원문 금지)
    AuditLogger.log_action(
        db,
        user.user_id,
        "TAX_INVOICE_IMPORT",
        target_type="TAX_INVOICE",
        new_value="total={0}, created={1}, duplicate={2}, held={3}".format(
            result["total"], result["created"], result["duplicate"], result["held"]
        ),
    )
    db.commit()
    return schemas.TaxInvoiceCommitResponse(**result)


@router.post("/rematch", response_model=schemas.TaxInvoiceRematchResult)
def rematch_tax_invoices(
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """미매칭 세금계산서 재매칭 — 나중에 등록된 고객사/투자사에 상대 사업자번호로 재연결."""
    result = tax_invoice_import.rematch_unmatched(db)
    AuditLogger.log_action(
        db, user.user_id, "TAX_INVOICE_REMATCH", target_type="TAX_INVOICE",
        new_value="scanned={0}, client={1}, buyer={2}".format(
            result["scanned"], result["relinked_client"], result["relinked_buyer"]),
    )
    db.commit()
    return schemas.TaxInvoiceRematchResult(**result)


def _resolve_scan_folder(db: Session, folder: Optional[str]) -> str:
    f = (folder or "").strip() or tax_invoice_import.scan_folder_default(db)
    if not f:
        raise HTTPException(status_code=422, detail="스캔할 Dropbox 폴더가 지정되지 않았습니다")
    if not dropbox_storage.is_configured():
        raise HTTPException(status_code=503, detail="Dropbox 연동이 설정되지 않았습니다")
    return f


@router.post("/scan/preview", response_model=schemas.TaxInvoicePreviewResponse)
def scan_preview_tax_invoices(
    folder: Optional[str] = Query(None, description="스캔 Dropbox 폴더(미지정 시 config 기본값)"),
    _: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """Dropbox 정산 폴더(하위 포함) .html 스캔 → 미리보기(DB 무변경)."""
    f = _resolve_scan_folder(db, folder)
    try:
        files = tax_invoice_import.scan_dropbox_html(f)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return schemas.TaxInvoicePreviewResponse(items=tax_invoice_import.analyze_files(db, files))


@router.post("/scan/commit", response_model=schemas.TaxInvoiceCommitResponse)
def scan_commit_tax_invoices(
    folder: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """Dropbox 정산 폴더 .html 스캔 → 원장 적재(승인번호 멱등)."""
    f = _resolve_scan_folder(db, folder)
    try:
        files = tax_invoice_import.scan_dropbox_html(f)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    result = tax_invoice_import.commit_files(
        db, files, actor_id=user.user_id, project_id=(project_id or None)
    )
    AuditLogger.log_action(
        db,
        user.user_id,
        "TAX_INVOICE_SCAN_IMPORT",
        target_type="TAX_INVOICE",
        new_value="folder scan — total={0}, created={1}, duplicate={2}, held={3}".format(
            result["total"], result["created"], result["duplicate"], result["held"]
        ),
    )
    db.commit()
    return schemas.TaxInvoiceCommitResponse(**result)


@router.delete("/{tax_invoice_id}", status_code=204)
def delete_tax_invoice(
    tax_invoice_id: str,
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """원장 항목 삭제(정정용)."""
    row = db.get(TaxInvoice, tax_invoice_id)
    if row is None:
        raise HTTPException(status_code=404, detail="세금계산서를 찾을 수 없습니다")
    approval_no = row.approval_no
    db.delete(row)
    AuditLogger.log_action(
        db, user.user_id, "TAX_INVOICE_DELETE", target_type="TAX_INVOICE",
        target_id=tax_invoice_id, old_value="approval_no={0}".format(approval_no or ""),
    )
    db.commit()
