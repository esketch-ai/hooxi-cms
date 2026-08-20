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
from services import tax_invoice_import
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
