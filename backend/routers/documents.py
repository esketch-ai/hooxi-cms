"""문서 아카이브 — SCR-13 (P1). 업로드는 storage(GCS 또는 로컬 폴백) 경유."""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

import schemas
from auth import get_current_user, require_permission
from models import ActivityHistory, Asset, Client, Document, User, get_db
from routers import common
from services import client_folders, storage
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/documents", tags=["documents"])

_DOC_TYPES = ("CONTRACT", "REPORT", "FORM", "PHOTO", "SIGN", "ETC")

# 업로드 유형 → 고객사 폴더의 6구분(tb_code CLIENT_FOLDER) 코드 매핑.
# 실제 폴더명은 라벨을 해석해 사용(하드코딩 금지) → provision된 서브폴더와 동일 위치.
DOC_TYPE_TO_FOLDER_CODE = {
    "CONTRACT": "CONTRACT",   # 계약서
    "REPORT": "REPORT",       # 보고서
    "PHOTO": "ASSET_AUTH",    # 현장사진 → 자산·인증정보
    "SIGN": "EVIDENCE",       # 서명 → 증빙자료
    "FORM": "EVIDENCE",       # 양식 → 증빙자료
    "ETC": "EVIDENCE",        # 기타 → 증빙자료
}

# 업로드 파일 크기 상한 — 태블릿 현장 사진·서명 기준 25MB
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def storage_folder(db: Session, client: Optional[Client], doc_type: str) -> str:
    """업로드 저장 폴더(root 제외 상대경로) — 고객사 폴더(회사명_짧은ID)/매핑된 6구분 라벨.

    고객사 폴더(provision과 동일한 folder_name) 아래 매핑 라벨에 저장한다. 고객사 미지정
    (공용 양식 등)은 _공용/{라벨}. 라벨은 tb_code CLIENT_FOLDER에서 해석.
    """
    code = DOC_TYPE_TO_FOLDER_CODE.get(doc_type, "EVIDENCE")
    label = client_folders.subfolder_label_for_code(db, code) or "증빙자료"
    # provision된 폴더(dropbox_folder) 기준 — 회사명 개명 후에도 같은 폴더로 저장
    base = client_folders.upload_base(db, client)
    return "{0}/{1}".format(base, label)


@router.get("", response_model=schemas.DocumentListResponse)
def list_documents(
    client_id: Optional[str] = Query(None, description="고객사"),
    doc_type: Optional[str] = Query(None, description="CONTRACT/REPORT/FORM/PHOTO/SIGN/ETC"),
    history_id: Optional[str] = Query(None, description="활동 이력"),
    asset_id: Optional[str] = Query(None, description="자산"),
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
    if history_id:
        query = query.filter(Document.history_id == history_id)
    if asset_id:
        query = query.filter(Document.asset_id == asset_id)
    if date_from:
        query = query.filter(Document.created_at >= common.kst_day_start_utc(date_from))
    if date_to:
        query = query.filter(Document.created_at <= common.kst_day_end_utc(date_to))
    if search:
        query = query.filter(
            Document.title.ilike(
                "%{0}%".format(common.escape_like(search.strip())), escape="\\"
            )
        )

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
    asset_id: Optional[str] = Form(None),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """문서 업로드 (multipart) — client_id 없으면 공용 양식(R2-C6)."""
    if doc_type not in _DOC_TYPES:
        raise HTTPException(status_code=422, detail="doc_type은 CONTRACT/REPORT/FORM/PHOTO/SIGN/ETC 중 하나여야 합니다")
    client = None
    if client_id:
        client = common.get_or_404(db, Client, client_id, "고객사")
    if history_id:
        common.get_or_404(db, ActivityHistory, history_id, "활동 이력")
    if asset_id:
        asset = common.get_or_404(db, Asset, asset_id, "자산")
        # 자산-고객사 소유 검증 (P1-C) — 다른 고객사 자산에 문서가 연결되는 정합성 붕괴 방지
        if client_id and asset.client_id != client_id:
            raise HTTPException(
                status_code=422, detail="연결 자산이 해당 고객사의 자산이 아닙니다"
            )
        # 자산만 주어지고 고객사 미지정이면 자산 소유 고객사로 귀속 — client_id 없는 고아 문서 방지(L2)
        if not client_id:
            client_id = asset.client_id
            client = db.get(Client, client_id)

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="빈 파일은 업로드할 수 없습니다")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기가 25MB를 초과합니다")
    file_url = storage.save_file(
        content,
        file.filename or "document",
        folder=storage_folder(db, client, doc_type),
    )

    doc = Document(
        client_id=client_id,
        doc_type=doc_type,
        title=title or (file.filename or "문서"),
        file_url=file_url,
        version=1,
        history_id=history_id,
        asset_id=asset_id,
        uploaded_by=user.user_id,
    )
    db.add(doc)
    db.flush()  # gen_uuid PK 확보 후 감사 로그 target_id로 사용
    AuditLogger.document_upload(
        db, user.user_id, doc.doc_id, "{0}: {1}".format(doc_type, doc.title)
    )
    db.commit()
    db.refresh(doc)
    return common.build_document_outs(db, [doc])[0]


@router.get("/{doc_id}/download")
def download_document(
    doc_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """다운로드 — GCS는 서명 URL 리다이렉트, 로컬은 파일 응답. 감사 로그 기록."""
    doc = common.get_or_404(db, Document, doc_id, "문서")
    try:
        url = storage.get_url(doc.file_url)
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not url:
        raise HTTPException(status_code=404, detail="저장소에서 파일을 찾을 수 없습니다")
    AuditLogger.document_download(db, user.user_id, doc.doc_id)
    db.commit()
    if url.startswith("http://") or url.startswith("https://"):
        return RedirectResponse(url)
    return FileResponse(url, filename=doc.title or "document")


# 삭제 허용 유형 — 오촬영/오등록 정리용. 리포트(REPORT)·서명(SIGN)은 보존을 위해 제외.
_DELETABLE_DOC_TYPES = ("CONTRACT", "FORM", "PHOTO", "ETC")


@router.delete("/{doc_id}", response_model=schemas.MessageResponse)
def delete_document(
    doc_id: str,
    user: User = Depends(require_permission("client.delete")),
    db: Session = Depends(get_db),
):
    """문서 삭제 (MANAGER 이상) — 현장사진·제원표·일반문서 오등록 정리용.

    리포트 발송 파일(REPORT)·고객 확인 서명(SIGN)은 발송/증빙 보존을 위해 삭제 불가(403).
    저장소 파일도 best-effort로 제거하고(실패해도 레코드는 삭제) 감사 로그를 남긴다.
    """
    doc = common.get_or_404(db, Document, doc_id, "문서")
    if doc.doc_type not in _DELETABLE_DOC_TYPES:
        raise HTTPException(
            status_code=403,
            detail="리포트·서명 문서는 보존 대상이라 삭제할 수 없습니다",
        )
    # 저장소 파일 제거 — 실패(미설정·일시 오류)해도 레코드 삭제는 진행(고아 레코드보다 UI 정합 우선)
    try:
        storage.delete_file(doc.file_url)
    except storage.StorageError:
        pass
    AuditLogger.log_action(
        db,
        user.user_id,
        "DOCUMENT_DELETE",
        target_type="DOCUMENT",
        target_id=doc_id,
        old_value="{0}: {1}".format(doc.doc_type, doc.title),
    )
    db.delete(doc)
    db.commit()
    return schemas.MessageResponse(message="문서가 삭제되었습니다")
