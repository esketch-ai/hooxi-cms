"""연동 설정 관리 API — SCR-14 연동 탭 (전부 ADMIN 전용, §10.1).

- GET  /integrations                     — REGISTRY 기반 연동·필드 상태(값 미노출)
- PUT  /integrations/{name}              — 전달된 키만 갱신(null=삭제), 시크릿 암호화 저장
- POST /integrations/{name}/test         — 실연결 테스트 {ok, message}
- GET  /integrations/kakao_bot/webhook-url — 오픈빌더 등록용 전체 URL(감사 INTEGRATION_REVEAL)
- POST /integrations/dropbox/oauth/authorize-url / exchange — Dropbox OAuth 마법사

시크릿 취급 규약(R2-E6): 응답·이력(tb_config_history)·감사 로그 어디에도 시크릿
원문을 남기지 않는다 — 이력은 "***" 마스킹, 감사 로그는 변경 키 이름 목록만.
"""

import smtplib

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import schemas
from auth import require_role
from models import ConfigHistory, User, get_db
from services import dropbox_storage, email_service, integration_config, kakao_service
from services.audit_logger import AuditLogger
from services.integration_config import REGISTRY

router = APIRouter(prefix="/integrations", tags=["integrations"])

SOLAPI_BALANCE_URL = "https://api.solapi.com/cash/v1/balance"
DROPBOX_AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
DROPBOX_TOKEN_URL = "https://api.dropbox.com/oauth2/token"

WEBHOOK_PATH = "/api/v1/kakao/webhook"

TEST_TIMEOUT = 10.0


def _require_name(name: str) -> dict:
    spec = REGISTRY.get(name)
    if spec is None:
        raise HTTPException(status_code=404, detail="알 수 없는 연동입니다: {0}".format(name))
    return spec


def _webhook_url(masked: bool = True) -> str:
    """카카오 웹훅 URL — masked=True면 시크릿을 ***로 가린다."""
    base = kakao_service.app_base_url()
    secret = integration_config.resolve("KAKAO_WEBHOOK_SECRET")
    shown = "***" if masked else (secret or "")
    return "{0}{1}?secret={2}".format(base, WEBHOOK_PATH, shown)


def _integration_out(name: str) -> schemas.IntegrationOut:
    spec = _require_name(name)
    field_status = integration_config.status(name)
    fields = [
        schemas.IntegrationFieldOut(
            key=field.key,
            label=field.label,
            secret=field.secret,
            required=field.required,
            configured=field_status[field.key]["configured"],
            source=field_status[field.key]["source"],
        )
        for field in spec["fields"]
    ]
    return schemas.IntegrationOut(
        name=name,
        label=spec["label"],
        fields=fields,
        webhook_url=_webhook_url(masked=True) if name == "kakao_bot" else None,
    )


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------
@router.get("", response_model=schemas.IntegrationListResponse)
def list_integrations(_: User = Depends(require_role("ADMIN"))):
    """연동 전체 목록 — 필드별 configured/source만 노출(시크릿·값 미노출)."""
    return schemas.IntegrationListResponse(
        items=[_integration_out(name) for name in REGISTRY]
    )


@router.get("/kakao_bot/webhook-url", response_model=schemas.IntegrationWebhookUrlOut)
def get_kakao_webhook_url(
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """오픈빌더 스킬 서버 등록용 전체 웹훅 URL(시크릿 포함) — 열람 감사 기록."""
    secret = integration_config.resolve("KAKAO_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(
            status_code=422,
            detail="카카오 웹훅 시크릿(KAKAO_WEBHOOK_SECRET)이 설정되지 않았습니다. 먼저 저장하세요.",
        )
    AuditLogger.integration_reveal(db, admin.user_id, "kakao_bot", "webhook_url")
    db.commit()
    return schemas.IntegrationWebhookUrlOut(url=_webhook_url(masked=False))


# ---------------------------------------------------------------------------
# 저장 — 전달된 키만 갱신, 시크릿 암호화, 이력 마스킹, 감사는 키 목록만
# ---------------------------------------------------------------------------
@router.put("/{name}", response_model=schemas.IntegrationOut)
def update_integration(
    name: str,
    payload: schemas.IntegrationUpdate,
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    _require_name(name)
    if not isinstance(payload.values, dict) or not payload.values:
        raise HTTPException(status_code=422, detail="변경할 값(values)이 없습니다")

    row, old_masked, new_masked, changed_keys = integration_config.apply_updates(
        db, name, payload.values, admin.user_id
    )
    if changed_keys:
        db.add(
            ConfigHistory(
                config_key=row.config_key,
                old_value=old_masked,
                new_value=new_masked,
                updated_by=admin.user_id,
            )
        )
        AuditLogger.integration_change(db, admin.user_id, name, changed_keys)
    db.commit()
    integration_config.bump_version()
    return _integration_out(name)


# ---------------------------------------------------------------------------
# 연결 테스트 — {ok, message}. 실패 사유에 자격증명 원문 노출 금지
# ---------------------------------------------------------------------------
def _test_dropbox() -> schemas.IntegrationTestOut:
    if not dropbox_storage.is_configured():
        return schemas.IntegrationTestOut(
            ok=False,
            message="Dropbox 설정이 완료되지 않았습니다 — 앱 키·시크릿·리프레시 토큰을 저장하세요.",
        )
    try:
        dbx = dropbox_storage._get_client()
        account = dbx.users_get_current_account()
        email = getattr(account, "email", None) or "알 수 없음"
        is_team = bool(getattr(account, "team", None))
        return schemas.IntegrationTestOut(
            ok=True,
            message="Dropbox 연결 성공 — 계정: {0}{1}".format(
                email, " (팀 계정)" if is_team else ""
            ),
        )
    except dropbox_storage.DropboxConfigError as exc:
        return schemas.IntegrationTestOut(ok=False, message=str(exc))
    except Exception:
        return schemas.IntegrationTestOut(
            ok=False,
            message="Dropbox 연결에 실패했습니다 — 자격증명이 올바른지 확인하세요.",
        )


def _test_gmail() -> schemas.IntegrationTestOut:
    sender = integration_config.resolve("GMAIL_SENDER")
    app_password = integration_config.resolve("GMAIL_APP_PASSWORD")
    if not (sender and app_password):
        return schemas.IntegrationTestOut(
            ok=False,
            message="Gmail 설정이 완료되지 않았습니다 — 발신 이메일과 앱 비밀번호를 저장하세요.",
        )
    try:
        with smtplib.SMTP_SSL(
            email_service.SMTP_HOST, email_service.SMTP_PORT, timeout=TEST_TIMEOUT
        ) as smtp:
            smtp.login(sender, app_password)
        return schemas.IntegrationTestOut(
            ok=True, message="Gmail SMTP 로그인 성공 — {0}".format(sender)
        )
    except smtplib.SMTPAuthenticationError:
        return schemas.IntegrationTestOut(
            ok=False,
            message="Gmail 로그인에 실패했습니다 — 앱 비밀번호(2단계 인증 후 발급)를 확인하세요.",
        )
    except Exception:
        return schemas.IntegrationTestOut(
            ok=False, message="Gmail SMTP 서버 연결에 실패했습니다 — 잠시 후 다시 시도하세요."
        )


def _test_solapi() -> schemas.IntegrationTestOut:
    api_key = integration_config.resolve("SOLAPI_API_KEY")
    api_secret = integration_config.resolve("SOLAPI_API_SECRET")
    if not (api_key and api_secret):
        return schemas.IntegrationTestOut(
            ok=False,
            message="SOLAPI 설정이 완료되지 않았습니다 — API 키와 시크릿을 저장하세요.",
        )
    try:
        headers = {
            "Authorization": kakao_service._solapi_auth_header(api_key, api_secret)
        }
        resp = httpx.get(SOLAPI_BALANCE_URL, headers=headers, timeout=TEST_TIMEOUT)
    except Exception:
        return schemas.IntegrationTestOut(
            ok=False, message="SOLAPI 서버 연결에 실패했습니다 — 잠시 후 다시 시도하세요."
        )
    if resp.status_code == 200:
        balance = (resp.json() or {}).get("balance")
        suffix = " — 잔액 {0}원".format(balance) if balance is not None else ""
        return schemas.IntegrationTestOut(ok=True, message="SOLAPI 인증 성공{0}".format(suffix))
    return schemas.IntegrationTestOut(
        ok=False,
        message="SOLAPI 인증에 실패했습니다 (HTTP {0}) — API 키·시크릿을 확인하세요.".format(
            resp.status_code
        ),
    )


def _test_required_fields(name: str) -> schemas.IntegrationTestOut:
    """실연결 검증 수단이 없는 연동 — 필수값 존재 확인만."""
    spec = REGISTRY[name]
    field_status = integration_config.status(name)
    missing = [
        f.key for f in spec["fields"] if f.required and not field_status[f.key]["configured"]
    ]
    if missing:
        return schemas.IntegrationTestOut(
            ok=False, message="필수 설정이 비어 있습니다: {0}".format(", ".join(missing))
        )
    return schemas.IntegrationTestOut(
        ok=True, message="{0} 필수 설정이 모두 입력되었습니다.".format(spec["label"])
    )


@router.post("/{name}/test", response_model=schemas.IntegrationTestOut)
def test_integration(name: str, _: User = Depends(require_role("ADMIN"))):
    _require_name(name)
    if name == "dropbox":
        return _test_dropbox()
    if name == "gmail":
        return _test_gmail()
    if name == "solapi":
        return _test_solapi()
    return _test_required_fields(name)  # kakao_bot · naver_works


# ---------------------------------------------------------------------------
# Dropbox OAuth 마법사 — authorize URL 발급 → code 교환 → refresh token 저장
# ---------------------------------------------------------------------------
@router.post("/dropbox/oauth/authorize-url", response_model=schemas.DropboxAuthorizeUrlOut)
def dropbox_authorize_url(_: User = Depends(require_role("ADMIN"))):
    app_key = integration_config.resolve("DROPBOX_APP_KEY")
    if not app_key:
        raise HTTPException(
            status_code=422,
            detail="Dropbox 앱 키(DROPBOX_APP_KEY)가 설정되지 않았습니다. 먼저 저장하세요.",
        )
    url = "{0}?client_id={1}&response_type=code&token_access_type=offline".format(
        DROPBOX_AUTHORIZE_URL, app_key
    )
    return schemas.DropboxAuthorizeUrlOut(url=url)


@router.post("/dropbox/oauth/exchange", response_model=schemas.IntegrationTestOut)
def dropbox_oauth_exchange(
    payload: schemas.DropboxOAuthExchangeRequest,
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    """인증 코드 → refresh token 교환·암호화 저장 → 즉시 연결 테스트 결과 반환."""
    app_key = integration_config.resolve("DROPBOX_APP_KEY")
    app_secret = integration_config.resolve("DROPBOX_APP_SECRET")
    if not (app_key and app_secret):
        raise HTTPException(
            status_code=422,
            detail="Dropbox 앱 키·시크릿이 설정되지 않았습니다. 먼저 저장한 뒤 다시 시도하세요.",
        )

    try:
        resp = httpx.post(
            DROPBOX_TOKEN_URL,
            data={"code": payload.code.strip(), "grant_type": "authorization_code"},
            auth=(app_key, app_secret),
            timeout=15.0,
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Dropbox 서버에 연결할 수 없습니다 — 잠시 후 다시 시도하세요.",
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=(
                "Dropbox 토큰 교환에 실패했습니다 (HTTP {0}) — "
                "인증 코드가 만료되었거나 잘못되었습니다. 다시 발급받아 시도하세요.".format(
                    resp.status_code
                )
            ),
        )
    refresh_token = (resp.json() or {}).get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=502,
            detail=(
                "Dropbox 토큰 응답에 refresh_token이 없습니다 — "
                "authorize URL에 token_access_type=offline이 포함되었는지 확인하세요."
            ),
        )

    row, old_masked, new_masked, changed_keys = integration_config.apply_updates(
        db, "dropbox", {"DROPBOX_REFRESH_TOKEN": refresh_token}, admin.user_id
    )
    db.add(
        ConfigHistory(
            config_key=row.config_key,
            old_value=old_masked,
            new_value=new_masked,
            updated_by=admin.user_id,
        )
    )
    AuditLogger.integration_change(db, admin.user_id, "dropbox", changed_keys)
    db.commit()
    integration_config.bump_version()

    return _test_dropbox()
