"""엑셀 일괄 등록 — 고객사(SCR-03)·자산(SCR-04) 양식 다운로드/미리보기/반영.

컬럼 규격은 services/import_spec.py 단일 원천 — 양식·파싱·spec 응답이 전부
같은 규격에서 파생된다(라벨 변경은 그 파일 1곳 수정으로 끝).

- 권한: master.write (단건 등록과 동일)
- preview는 DB 무변경, commit은 같은 파일을 전체 재검증(무상태) 후
  유효 행만 단일 트랜잭션으로 부분 반영한다.
- 인증 비밀값 컬럼 없음 — 자산은 인증정보 없이 생성(개별 화면에서 암호화 입력).
"""

from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

import schemas
from auth import require_permission
from models import Asset, Client, User, get_db
from routers import common
from routers.assets import _ASSET_FIELDS
from routers.clients import _CLIENT_FIELDS, _provision_dropbox_folder_bg
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
    "transport_roster": lambda p: Client(**{f: getattr(p, f) for f in _CLIENT_FIELDS}),
    "transport_info": lambda p: Client(**{f: getattr(p, f) for f in _CLIENT_FIELDS}),
    "transport": lambda p: Client(**{f: getattr(p, f) for f in _CLIENT_FIELDS}),
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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(require_permission("master.write")),
    db: Session = Depends(get_db),
):
    """반영 — 같은 파일 전체 재검증(무상태) 후 유효 행만 단일 트랜잭션 부분 반영.

    오류 행은 건너뛰고(errors로 안내) 감사 로그 EXCEL_IMPORT에 건수 요약만
    기록한다(행 내용·연락처 등 원문 기록 금지 — R2-E6 취지).
    고객사 일괄 등록은 단건 등록과 동일하게 응답 후 Dropbox 전용 폴더를
    백그라운드로 provision한다(best-effort — 미설정·실패는 반영에 무영향).
    """
    content = await _read_upload(file)
    result = excel_import.parse_and_validate(db, entity, content)
    factory = _ROW_FACTORY.get(entity)
    if factory is None:  # get_spec에서 404가 먼저 나지만 방어적으로 유지
        raise HTTPException(status_code=404, detail="지원하지 않는 일괄 등록 대상입니다")

    valid = result.valid_rows
    created_rows = []
    promoted_ids = []  # 대기→정식 승격(사업자번호 새로 채워진 기존 건) — 커밋 후 폴더 provision
    updated_count = 0
    # 운수사 표준/정보 upsert — 중복 제거 키 = 사업자번호(정규화) 우선, 없으면 회사명.
    # 사업자번호가 있으면 그 기준으로 기존 운수사를 찾아 보강(회사명 표기가 달라도 동일 법인으로 병합),
    # 없으면 회사명(정제)으로 매칭. 파일 내 중복도 같은 키로 하나에 병합한다.
    upsert = entity in ("transport_info", "transport")
    # 기존 운수사 인덱스를 1회 로드(사업자번호 정규화·회사명) — 행마다 전체스캔 방지.
    by_biz: dict = {}
    by_name: dict = {}
    if upsert:
        for c in db.query(Client).filter(Client.client_type == "TRANSPORT").all():
            nb = common.normalize_biz_no(c.biz_reg_no)
            if nb:
                by_biz.setdefault(nb, c)
            by_name.setdefault((c.company_name or "").strip(), c)

    def _find_existing(p):
        norm = common.normalize_biz_no(getattr(p, "biz_reg_no", None))
        if norm and norm in by_biz:
            return by_biz[norm]
        name = (p.company_name or "").strip()
        if norm:
            # 사업자번호는 있으나 아직 미매칭 — 이름으로도 확인(이름 매칭 후 번호 보강 케이스)
            return by_name.get(name)
        return by_name.get(name)

    def _remember(p, obj):
        norm = common.normalize_biz_no(getattr(p, "biz_reg_no", None))
        if norm:
            by_biz[norm] = obj
        by_name[(p.company_name or "").strip()] = obj

    for parsed in valid:
        p = parsed.payload
        existing = _find_existing(p) if upsert else None
        if existing is not None:
            # 중복 병합 — 기존에 '비어있는' 필드만 새 값으로 채운다(덮어쓰기 없음, 기존 유지).
            # 사업자번호가 새로 채워지면 승격 대상으로 표시(정식 전환 + 폴더 provision).
            had_biz = bool(common.normalize_biz_no(existing.biz_reg_no))
            changed = False
            for f in _CLIENT_FIELDS:
                if f == "client_type":
                    continue
                new_val = getattr(p, f, None)
                cur = getattr(existing, f, None)
                cur_empty = cur is None or (isinstance(cur, str) and not cur.strip())
                if new_val is not None and cur_empty:
                    setattr(existing, f, new_val)
                    changed = True
            now_biz = bool(common.normalize_biz_no(existing.biz_reg_no))
            if now_biz and not had_biz and not existing.dropbox_folder:
                promoted_ids.append(existing)  # 커밋 후 client_id로 provision 예약
            if upsert:
                _remember(p, existing)
            updated_count += 1 if changed else 0
        else:
            row = factory(p)
            db.add(row)
            created_rows.append(row)
            if upsert:
                _remember(p, row)
    error_rows = [r for r in result.rows if r.errors]
    AuditLogger.log_action(
        db,
        user.user_id,
        "EXCEL_IMPORT",
        target_type=result.spec.entity.upper().rstrip("S"),  # CLIENT/ASSET
        new_value="{0} 일괄 등록 — 생성 {1}건 / 갱신 {2}건 / 건너뜀 {3}건 (총 {4}행)".format(
            result.spec.label, len(created_rows), updated_count, len(error_rows), len(result.rows)
        ),
    )
    db.commit()
    # Dropbox 폴더 provision — 신규 생성분 + 대기→정식 승격분. 사업자번호 게이트는 provision
    # 내부에서 최종 확인하므로, 사업자번호 없는 '대기' 건은 예약돼도 폴더가 만들어지지 않는다.
    if entity in ("clients", "transport_roster", "transport_info", "transport"):
        for row in list(created_rows) + list(promoted_ids):
            client_id = getattr(row, "client_id", None)
            if client_id:
                background_tasks.add_task(
                    _provision_dropbox_folder_bg, client_id, user.user_id
                )
    return schemas.ImportCommitOut(
        entity=result.spec.entity,
        created=len(created_rows),
        updated=updated_count,
        skipped=len(error_rows),
        errors=[excel_import.row_result(r) for r in error_rows],
    )
