"""문서 아카이브 — SCR-13 (P1). 업로드는 storage(GCS 또는 로컬 폴백) 경유."""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import ActivityHistory, Client, Document, User, get_db
from routers import common
from services import storage

router = APIRouter(prefix="/documents", tags=["documents"])

_DOC_TYPES = ("CONTRACT", "REPORT", "FORM", "PHOTO", "ETC")


@router.get("", response_model=schemas.DocumentListResponse)
def list_documents(
    client_id: Optional[str] = Query(None, description="고객사"),
    doc_type: Optional[str] = Query(None, description="CONTRACT/REPORT/FORM/PHOTO/ETC"),
    date_from: Optional[date] = Query(None, description="업로드 기간 시작"),
    date_to: Optional[date] = Query(None, description="업로드 기간 끝"),
    search: Optional[str] = Query(None, description="문서명 검색"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """문서 목록 — 고객사·문서 유형·기간 필터."""
    query = db.query(Document)
    if client_id:
        query = query.filter(Document.client_id == client_id)
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)
    if date_from:
        query = query.filter(Document.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Document.created_at <= datetime.combine(date_to, datetime.max.time()))
    if search:
        query = query.filter(Document.title.ilike("%{0}%".format(search.strip())))

    total = query.count()
    rows = (
        query.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.DocumentListResponse(items=common.build_document_outs(db, rows), total=total)


@router.post("", response_model=schemas.DocumentOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form("ETC"),
    title: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    history_id: Optional[str] = Form(None),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """문서 업로드 (multipart) — client_id 없으면 공용 양식(R2-C6)."""
    if doc_type not in _DOC_TYPES:
        raise HTTPException(status_code=422, detail="doc_type은 CONTRACT/REPORT/FORM/PHOTO/ETC 중 하나여야 합니다")
    if client_id:
        common.get_or_404(db, Client, client_id, "고객사")
    if history_id:
        common.get_or_404(db, ActivityHistory, history_id, "활동 이력")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="빈 파일은 업로드할 수 없습니다")
    file_url = storage.save_file(content, file.filename or "document", folder="documents")

    doc = Document(
        client_id=client_id,
        doc_type=doc_type,
        title=title or (file.filename or "문서"),
        file_url=file_url,
        version=1,
        history_id=history_id,
        uploaded_by=user.user_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return common.build_document_outs(db, [doc])[0]


@router.get("/{doc_id}/download")
def download_document(
    doc_id: str,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """다운로드 — GCS는 서명 URL 리다이렉트, 로컬은 파일 응답."""
    doc = common.get_or_404(db, Document, doc_id, "문서")
    try:
        url = storage.get_url(doc.file_url)
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not url:
        raise HTTPException(status_code=404, detail="저장소에서 파일을 찾을 수 없습니다")
    if url.startswith("http://") or url.startswith("https://"):
        return RedirectResponse(url)
    return FileResponse(url, filename=doc.title or "document")
