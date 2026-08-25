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
from models import TaxInvoice, User, get_db
from services import dropbox_storage, tax_invoice_import
from services.audit_logger import AuditLogger

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


@router.get("", response_model=schemas.TaxInvoiceListResponse)
def list_tax_invoices(
    direction: Optional[str] = Query(None, description="매입/매출/미상"),
    search: Optional[str] = Query(None, description="상대 사업자번호·상호 부분검색"),
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
