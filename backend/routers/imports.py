"""엑셀 일괄 등록 — 고객사(SCR-03)·자산(SCR-04) 양식 다운로드/미리보기/반영.

컬럼 규격은 services/import_spec.py 단일 원천 — 양식·파싱·spec 응답이 전부
같은 규격에서 파생된다(라벨 변경은 그 파일 1곳 수정으로 끝).

- 권한: master.write (단건 등록과 동일)
- preview는 DB 무변경, commit은 같은 파일을 전체 재검증(무상태) 후
  유효 행만 단일 트랜잭션으로 부분 반영한다.
- 인증 비밀값 컬럼 없음 — 자산은 인증정보 없이 생성(개별 화면에서 암호화 입력).
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

import schemas
from auth import require_permission
from models import Asset, Client, User, get_db
from routers.assets import _ASSET_FIELDS
from routers.clients import _CLIENT_FIELDS
from services import excel_import
from services.audit_logger import AuditLogger

router = APIRouter(prefix="/imports", tags=["imports"])

# 업로드 파일 크기 상한 — documents.py와 동일 기준(25MB)
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# 엔티티 → 모델 행 생성기 — 단건 등록 라우터의 필드 목록을 그대로 재사용해
# 생성 효과 동일 보장 (고객사=구독 없이 기본 생성, 자산=인증값 없이 생성)
_ROW_FACTORY = {
    "clients": lambda p: Client(**{f: getattr(p, f) for f in _CLIENT_FIELDS}),
    "assets": lambda p: Asset(**{f: getattr(p, f) for f in _ASSET_FIELDS}),
}


async def _read_upload(file: UploadFile) -> bytes:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="빈 파일은 업로드할 수 없습니다")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기가 25MB를 초과합니다")
    return content


@router.get("/{entity}/spec", response_model=schemas.ImportSpecOut)
def import_spec_info(
    entity: str,
    _: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """컬럼 안내 — 업로드 화면 가이드용 (미지 entity는 404)."""
    return excel_import.spec_out(db, entity)


@router.get("/{entity}/template")
def download_template(
    entity: str,
    _: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """양식(.xlsx) 다운로드 — 헤더(필수 * 표시)+예시 1행(코드 컬럼은 현재 라벨).

    파일명 한글은 RFC 5987 인코딩."""
    spec = excel_import.get_spec(entity)
    content = excel_import.build_template(db, entity)
    return Response(
        content=content,
        media_type=_XLSX_MEDIA_TYPE,
        headers={
            # 한글 파일명 — documents 다운로드와 동일 관용구(filename*=UTF-8'')
            "Content-Disposition": "attachment; filename*=UTF-8''{0}".format(
                quote(spec.filename)
            )
        },
    )


@router.post("/{entity}/preview", response_model=schemas.ImportPreviewOut)
async def preview_import(
    entity: str,
    file: UploadFile = File(...),
    _: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """미리보기 — 전 행 검증 결과만 반환, DB 무변경."""
    content = await _read_upload(file)
    result = excel_import.parse_and_validate(db, entity, content)
    return result.to_preview()


@router.post("/{entity}/commit", response_model=schemas.ImportCommitOut)
async def commit_import(
    entity: str,
    file: UploadFile = File(...),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """반영 — 같은 파일 전체 재검증(무상태) 후 유효 행만 단일 트랜잭션 부분 반영.

    오류 행은 건너뛰고(errors로 안내) 감사 로그 EXCEL_IMPORT에 건수 요약만
    기록한다(행 내용·연락처 등 원문 기록 금지 — R2-E6 취지).
    """
    content = await _read_upload(file)
    result = excel_import.parse_and_validate(db, entity, content)
    factory = _ROW_FACTORY.get(entity)
    if factory is None:  # get_spec에서 404가 먼저 나지만 방어적으로 유지
        raise HTTPException(status_code=404, detail="지원하지 않는 일괄 등록 대상입니다")

    valid = result.valid_rows
    for parsed in valid:
        db.add(factory(parsed.payload))
    error_rows = [r for r in result.rows if r.errors]
    AuditLogger.log_action(
        db,
        user.user_id,
        "EXCEL_IMPORT",
        target_type=result.spec.entity.upper().rstrip("S"),  # CLIENT/ASSET
        new_value="{0} 일괄 등록 — 생성 {1}건 / 건너뜀 {2}건 (총 {3}행)".format(
            result.spec.label, len(valid), len(error_rows), len(result.rows)
        ),
    )
    db.commit()
    return schemas.ImportCommitOut(
        entity=result.spec.entity,
        created=len(valid),
        skipped=len(error_rows),
        errors=[excel_import.row_result(r) for r in error_rows],
    )
