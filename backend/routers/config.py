"""시스템 설정(tb_config) 관리 — SCR-14 설정 탭 (§10.1: 사용자 관리·tb_config·백업 = ADMIN 전용).

- 알려진 키(sensitive_keywords 등)는 DB 미저장 시 코드 기본값을
  "기본값(미저장)"으로 노출해 화면에서 현재 유효값을 확인할 수 있게 한다.
- 값 변경 시 tb_config_history에 이전 값 기록(변경자·시각) +
  tb_audit_log(action=CONFIG_CHANGE) 적재.
"""

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import schemas
from auth import require_role
from models import Config, ConfigHistory, User, get_db
from routers import common
from routers.batch import DEFAULT_CHECK_AGENCIES
from routers.kakao import DEFAULT_SENSITIVE_KEYWORDS
from services.audit_logger import AuditLogger
from services.report_sender import DEFAULT_REPORT_MAIL_BODY, DEFAULT_REPORT_MAIL_SUBJECT

router = APIRouter(prefix="/config", tags=["config"])

# 알려진 키의 코드 기본값 — key: (기본값 객체, 설명)
KNOWN_DEFAULTS = {
    "sensitive_keywords": (
        DEFAULT_SENSITIVE_KEYWORDS,
        "카카오 AI 응대 민감 키워드 — 감지 시 담당자 연결 (CR-3)",
    ),
    "account_check_agencies": (
        DEFAULT_CHECK_AGENCIES,
        "월초 계정 점검 좁히기 키워드 — 비우면 로그인 계정 보유 자산 전체 점검, "
        "키워드 지정 시 대상 기관명에 포함된 자산만",
    ),
    "report_mail_subject": (
        DEFAULT_REPORT_MAIL_SUBJECT,
        "보고서 발송 메일 제목 템플릿 — 변수: {고객사명} {기간} {연도} {월} {보고서유형} {담당자명} "
        "(구독별 오버라이드가 우선)",
    ),
    "report_mail_body": (
        DEFAULT_REPORT_MAIL_BODY,
        "보고서 발송 메일 본문 템플릿 — 변수: {고객사명} {기간} {연도} {월} {보고서유형} {담당자명} "
        "(구독별 오버라이드가 우선)",
    ),
}


def _default_out(key: str) -> schemas.ConfigOut:
    """DB 미저장 알려진 키 — 코드 기본값을 '기본값(미저장)'으로 표시."""
    default_value, description = KNOWN_DEFAULTS[key]
    return schemas.ConfigOut(
        config_key=key,
        config_value=json.dumps(default_value, ensure_ascii=False),
        description="{0} — 기본값(미저장)".format(description),
        is_default=True,
    )


def _config_out(db: Session, row: Config) -> schemas.ConfigOut:
    unames = common.user_name_map(db, [row.updated_by])
    out = schemas.ConfigOut.model_validate(row, from_attributes=True)
    return out.model_copy(update={"updated_by_name": unames.get(row.updated_by)})


def _validate_config_value(key: str, raw_value: str):
    """value JSON 파싱 검증 + 알려진 키 구조 검증 — 실패 시 422."""
    try:
        parsed = json.loads(raw_value)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422, detail="config_value는 파싱 가능한 JSON 문자열이어야 합니다"
        )

    if key == "sensitive_keywords":
        if (
            not isinstance(parsed, list)
            or not parsed
            or not all(isinstance(k, str) and k.strip() for k in parsed)
        ):
            raise HTTPException(
                status_code=422,
                detail="sensitive_keywords는 비어 있지 않은 문자열 배열이어야 합니다",
            )
    elif key == "account_check_agencies":
        # 빈 배열 허용 (= 전체 점검). 값이 있으면 모두 비지 않은 문자열이어야 함.
        if not isinstance(parsed, list) or not all(
            isinstance(k, str) and k.strip() for k in parsed
        ):
            raise HTTPException(
                status_code=422,
                detail="account_check_agencies는 문자열 배열이어야 합니다 (비우면 전체 점검)",
            )
    elif key in ("report_mail_subject", "report_mail_body"):
        # 메일 템플릿 — 비어 있지 않은 문자열 (JSON 문자열로 저장, 빈 템플릿은 발송 불능)
        if not isinstance(parsed, str) or not parsed.strip():
            raise HTTPException(
                status_code=422,
                detail="{0}은(는) 비어 있지 않은 문자열이어야 합니다".format(key),
            )
    return parsed


@router.get("", response_model=List[schemas.ConfigOut])
def list_configs(
    _: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """전체 설정 목록 — DB 저장분 + 알려진 키의 기본값(미저장) 포함."""
    rows = db.query(Config).order_by(Config.config_key.asc()).all()
    items = [_config_out(db, row) for row in rows]
    stored_keys = {row.config_key for row in rows}
    for key in KNOWN_DEFAULTS:
        if key not in stored_keys:
            items.append(_default_out(key))
    return sorted(items, key=lambda item: item.config_key)


@router.get("/{config_key}", response_model=schemas.ConfigOut)
def get_config(
    config_key: str,
    _: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """설정 단건 조회 — 미저장 알려진 키는 기본값(미저장) 반환."""
    row = db.get(Config, config_key)
    if row is not None:
        return _config_out(db, row)
    if config_key in KNOWN_DEFAULTS:
        return _default_out(config_key)
    raise HTTPException(status_code=404, detail="설정을 찾을 수 없습니다")


@router.put("/{config_key}", response_model=schemas.ConfigOut)
def update_config(
    config_key: str,
    payload: schemas.ConfigUpdate,
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """설정 값 변경(없으면 생성) — 이전 값 이력 적재 + CONFIG_CHANGE 감사 로그."""
    _validate_config_value(config_key, payload.config_value)

    row = db.get(Config, config_key)
    old_value = row.config_value if row is not None else None

    if row is None:
        row = Config(config_key=config_key)
        db.add(row)
    row.config_value = payload.config_value
    if payload.description is not None:
        row.description = payload.description
    elif row.description is None and config_key in KNOWN_DEFAULTS:
        row.description = KNOWN_DEFAULTS[config_key][1]
    row.updated_by = admin.user_id

    # 변경 이력 (tb_config_history) — 이전 값·변경자·시각
    db.add(
        ConfigHistory(
            config_key=config_key,
            old_value=old_value,
            new_value=payload.config_value,
            updated_by=admin.user_id,
        )
    )
    # 감사 로그 (tb_audit_log) — 설정값은 비밀정보가 아니므로 전/후 값 기록 (R2-E6 준수)
    AuditLogger.config_change(db, admin.user_id, config_key, old_value, payload.config_value)
    db.commit()
    db.refresh(row)
    return _config_out(db, row)


@router.get("/{config_key}/history", response_model=schemas.ConfigHistoryListResponse)
def get_config_history(
    config_key: str,
    _: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """설정 변경 이력 — 최근순."""
    query = db.query(ConfigHistory).filter(ConfigHistory.config_key == config_key)
    total = query.count()
    rows = query.order_by(ConfigHistory.created_at.desc()).all()
    unames = common.user_name_map(db, [h.updated_by for h in rows])
    items = [
        schemas.ConfigHistoryOut.model_validate(h, from_attributes=True).model_copy(
            update={"updated_by_name": unames.get(h.updated_by)}
        )
        for h in rows
    ]
    return schemas.ConfigHistoryListResponse(items=items, total=total)
