"""인증·인가 — SCR-10 (CR-1: 네이버웍스 OAuth SSO) + C2 토큰-권한 동기화 + §10.1 RBAC.

- 인증: 네이버웍스 OAuth(OIDC). SSO는 '인증'만 담당 — 세션·인가는 자체 JWT.
- JWT: access 8h / refresh 7d. payload의 role은 화면 표시용 —
  권한 판정은 항상 서버가 DB 기준으로 수행 (C2).
- PIN(R2-C11): 미팅 모드·reveal 게이트용. bcrypt 해시.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import bcrypt
import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

import schemas
from models import User, get_db
from services.integration_config import resolve

# --- JWT 설정 ---
_DEFAULT_JWT_SECRET = "dev-only-insecure-secret-change-me"
JWT_SECRET = os.getenv("JWT_SECRET", _DEFAULT_JWT_SECRET)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(hours=8)
REFRESH_TOKEN_TTL = timedelta(days=7)

# --- 네이버웍스 OAuth (CR-1) ---
# NW_CLIENT_ID / NW_CLIENT_SECRET / NW_REDIRECT_URI는 연동 설정(DB 우선 + env 폴백)
# — 호출 시점에 resolve()로 해석한다 (_require_works_config).
NW_AUTHORIZE_URL = "https://auth.worksmobile.com/oauth2/v2.0/authorize"
NW_TOKEN_URL = "https://auth.worksmobile.com/oauth2/v2.0/token"
NW_USERINFO_URL = "https://www.worksapis.com/v1.0/users/me"
ALLOWED_EMAIL_DOMAIN = os.getenv("ALLOWED_EMAIL_DOMAIN", "hooxipartners.com")
# OAuth 콜백 후 브라우저를 돌려보낼 프론트 오리진 — 프로덕션은 동일 오리진이라 기본 ""
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "")

# --- RBAC (§10.1) — 권한 매트릭스는 서버 상수로 관리해 차후 수정 용이하게 ---
ROLE_LEVEL = {"STAFF": 1, "MANAGER": 2, "ADMIN": 3}

PERMISSION_MATRIX = {
    # 기능 키: 허용 역할 목록
    "crm.read_write": ["STAFF", "MANAGER", "ADMIN"],        # 고객사·이력·이슈·일정·보고서 조회/기록
    "master.write": ["STAFF", "MANAGER", "ADMIN"],          # 고객사/자산/사업 등록·수정, 보고서 업로드·발송
    "settlement.change": ["MANAGER", "ADMIN"],              # 정산 상태 변경·청구서 발행 (SCR-07)
    "client.delete": ["MANAGER", "ADMIN"],                  # 고객사/사업 삭제
    "admin.users_config_backup": ["ADMIN"],                 # 사용자 관리·tb_config·백업
    "asset.reveal_auth": ["STAFF", "MANAGER", "ADMIN"],     # reveal-auth (감사 로그 필수)
}

bearer_scheme = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# JWT 발급·검증
# ---------------------------------------------------------------------------
def _create_token(user: User, token_type: str, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.user_id,
        "user_id": user.user_id,
        "role": user.role,  # 화면 표시용 — 권한 판정은 DB 기준 (C2)
        "token_version": user.token_version or 0,
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(user: User) -> str:
    return _create_token(user, "access", ACCESS_TOKEN_TTL)


def create_refresh_token(user: User) -> str:
    return _create_token(user, "refresh", REFRESH_TOKEN_TTL)


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=401, detail="잘못된 토큰 유형입니다")
    return payload


def _verify_user_from_payload(payload: dict, db: Session) -> User:
    """C2: DB 재조회 — status=ACTIVE·token_version 일치 확인. role 판정은 DB 기준."""
    user = db.get(User, payload.get("user_id"))
    if not user:
        raise HTTPException(status_code=401, detail="존재하지 않는 사용자입니다")
    if user.status != "ACTIVE":
        raise HTTPException(status_code=401, detail="비활성 또는 승인 대기 계정입니다")
    if (user.token_version or 0) != payload.get("token_version"):
        raise HTTPException(status_code=401, detail="토큰이 무효화되었습니다. 다시 로그인하세요")
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    payload = decode_token(credentials.credentials, "access")
    return _verify_user_from_payload(payload, db)


def require_role(min_role: str):
    """역할 하한 검사 — 예: require_role("MANAGER")는 MANAGER·ADMIN 허용."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if ROLE_LEVEL.get(user.role, 0) < ROLE_LEVEL.get(min_role, 99):
            raise HTTPException(status_code=403, detail="권한이 없습니다")
        return user

    return dependency


def require_permission(permission_key: str):
    """§10.1 매트릭스 기반 기능 단위 인가."""

    allowed = PERMISSION_MATRIX.get(permission_key, [])

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="권한이 없습니다")
        return user

    return dependency


def _token_response(user: User) -> schemas.TokenResponse:
    return schemas.TokenResponse(
        access_token=create_access_token(user),
        refresh_token=create_refresh_token(user),
        user=schemas.UserOut.model_validate(user, from_attributes=True).model_copy(
            update={"pin_set": bool(user.pin_hash)}
        ),
    )


# ---------------------------------------------------------------------------
# 네이버웍스 OAuth (CR-1)
# ---------------------------------------------------------------------------
def _require_works_config():
    """네이버웍스 OAuth 설정 해석(DB 우선 + env 폴백) — 미설정 시 501.

    반환: (client_id, client_secret, redirect_uri)
    """
    client_id = resolve("NW_CLIENT_ID")
    client_secret = resolve("NW_CLIENT_SECRET")
    redirect_uri = resolve("NW_REDIRECT_URI")
    if not (client_id and client_secret and redirect_uri):
        raise HTTPException(
            status_code=501,
            detail=(
                "네이버웍스 OAuth가 설정되지 않았습니다. "
                "NW_CLIENT_ID / NW_CLIENT_SECRET / NW_REDIRECT_URI 환경변수를 설정하세요. "
                "(네이버웍스 Developer Console 앱 등록 필요 — CR-1)"
            ),
        )
    return client_id, client_secret, redirect_uri


def _create_state_token() -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "type": "oauth_state",
        "nonce": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _verify_state_token(state: str):
    try:
        payload = jwt.decode(state, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="유효하지 않은 state 파라미터입니다 (CSRF 방지)")
    if payload.get("type") != "oauth_state":
        raise HTTPException(status_code=400, detail="유효하지 않은 state 파라미터입니다 (CSRF 방지)")


@router.get("/works/authorize", response_model=schemas.AuthorizeResponse)
def works_authorize():
    """네이버웍스 OAuth 시작 — 프론트가 리다이렉트할 URL 반환."""
    client_id, _, redirect_uri = _require_works_config()
    state = _create_state_token()
    params = httpx.QueryParams(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "user",
            "state": state,
        }
    )
    return schemas.AuthorizeResponse(authorize_url=f"{NW_AUTHORIZE_URL}?{params}", state=state)


@router.get("/works/callback")
async def works_callback(code: str, state: str, db: Session = Depends(get_db)):
    """code→token→userinfo → 도메인 검증 → 계정 매칭/JIT → 자체 JWT 발급."""
    client_id, client_secret, redirect_uri = _require_works_config()
    _verify_state_token(state)

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_resp = await client.post(
            NW_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="네이버웍스 토큰 발급에 실패했습니다")
        works_access_token = token_resp.json().get("access_token")
        if not works_access_token:
            raise HTTPException(status_code=502, detail="네이버웍스 토큰 응답이 올바르지 않습니다")

        userinfo_resp = await client.get(
            NW_USERINFO_URL, headers={"Authorization": f"Bearer {works_access_token}"}
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="네이버웍스 사용자 정보 조회에 실패했습니다")
        info = userinfo_resp.json()

    email = (info.get("email") or "").strip().lower()
    works_user_id = str(info.get("userId") or info.get("userExternalKey") or "")
    user_name = info.get("userName") or {}
    if isinstance(user_name, dict):
        name = f"{user_name.get('lastName', '')}{user_name.get('firstName', '')}".strip()
    else:
        name = str(user_name)

    # 도메인 검증 (CR-1): @hooxipartners.com 외 거부
    if not email or not email.endswith(f"@{ALLOWED_EMAIL_DOMAIN}"):
        raise HTTPException(status_code=403, detail="회사 계정으로만 로그인할 수 있습니다")

    user = None
    if works_user_id:
        user = db.query(User).filter(User.works_user_id == works_user_id).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()

    if user is None:
        # JIT 가입: status=PENDING, role=STAFF (ADMIN 승인 시 ACTIVE)
        user = User(
            email=email,
            works_user_id=works_user_id or None,
            auth_provider="NAVER_WORKS",
            name=name or email.split("@")[0],
            role="STAFF",
            status="PENDING",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif works_user_id and not user.works_user_id:
        user.works_user_id = works_user_id
        db.commit()

    # 브라우저 리다이렉트 플로우 — 토큰은 URL fragment(#)로 전달해 서버 로그에 남지 않게 함
    if user.status == "PENDING":
        return RedirectResponse(
            f"{FRONTEND_ORIGIN}/login#works=pending&email={quote(email)}", status_code=302
        )
    if user.status != "ACTIVE":
        return RedirectResponse(f"{FRONTEND_ORIGIN}/login#works=inactive", status_code=302)

    tokens = _token_response(user)
    fragment = (
        f"access_token={quote(tokens.access_token)}"
        f"&refresh_token={quote(tokens.refresh_token)}"
    )
    return RedirectResponse(f"{FRONTEND_ORIGIN}/login#{fragment}", status_code=302)


# ---------------------------------------------------------------------------
# 이메일+PIN 로그인 — 도메인 제한 (네이버웍스 미연동 기간의 기본 로그인 수단)
# ---------------------------------------------------------------------------
@router.post("/email-login", response_model=schemas.EmailLoginResponse)
def email_login(payload: schemas.EmailLoginRequest, db: Session = Depends(get_db)):
    """@ALLOWED_EMAIL_DOMAIN 계정 로그인.

    - 미등록 이메일: JIT 가입(PENDING) → 관리자 승인 필요
    - ACTIVE + PIN 미설정(최초 로그인): 즉시 토큰 발급 → 프론트가 PIN 설정 강제
    - ACTIVE + PIN 설정됨: PIN 검증 필수 (PIN이 비밀번호 역할)
    """
    email = payload.email.strip().lower()
    if not email.endswith(f"@{ALLOWED_EMAIL_DOMAIN}"):
        raise HTTPException(status_code=403, detail="회사 계정으로만 로그인할 수 있습니다")

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        # JIT 가입: status=PENDING, role=STAFF (네이버웍스 JIT와 동일 정책)
        user = User(
            email=email,
            auth_provider="EMAIL",
            name=email.split("@")[0],
            role="STAFF",
            status="PENDING",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if user.status == "PENDING":
        return schemas.EmailLoginResponse(
            status="PENDING",
            message="가입 요청이 접수되었습니다 — 관리자 승인 후 이용 가능합니다",
        )
    if user.status != "ACTIVE":
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다. 관리자에게 문의하세요")

    if user.pin_hash:
        pin = (payload.pin or "").strip()
        if not pin:
            return schemas.EmailLoginResponse(status="PIN_REQUIRED")
        if not bcrypt.checkpw(pin.encode(), user.pin_hash.encode()):
            raise HTTPException(status_code=401, detail="PIN이 올바르지 않습니다")

    tokens = _token_response(user)
    return schemas.EmailLoginResponse(
        status="OK",
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        user=tokens.user,
    )


# ---------------------------------------------------------------------------
# 개발용 로그인 (ENABLE_DEV_LOGIN=true 일 때만 — 기본 비활성)
# ---------------------------------------------------------------------------
@router.post("/dev-login", response_model=schemas.TokenResponse)
def dev_login(payload: schemas.DevLoginRequest, db: Session = Depends(get_db)):
    if os.getenv("ENABLE_DEV_LOGIN", "false").lower() != "true":
        raise HTTPException(status_code=404, detail="Not Found")
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    if not user or user.status != "ACTIVE":
        raise HTTPException(status_code=401, detail="ACTIVE 상태의 등록된 사용자가 아닙니다")
    return _token_response(user)


# ---------------------------------------------------------------------------
# 토큰 갱신 (C2: status·role·token_version 재검증)
# ---------------------------------------------------------------------------
@router.post("/refresh", response_model=schemas.TokenResponse)
def refresh_tokens(payload: schemas.RefreshRequest, db: Session = Depends(get_db)):
    token_payload = decode_token(payload.refresh_token, "refresh")
    user = _verify_user_from_payload(token_payload, db)  # INACTIVE·PENDING 갱신 거부
    return _token_response(user)


# ---------------------------------------------------------------------------
# PIN (R2-C11) — 미팅 모드·reveal 게이트용
# ---------------------------------------------------------------------------
@router.post("/pin", response_model=schemas.MessageResponse)
def set_pin(
    payload: schemas.PinRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pin = payload.pin.strip()
    if not (pin.isdigit() and 4 <= len(pin) <= 6):
        raise HTTPException(status_code=422, detail="PIN은 4~6자리 숫자여야 합니다")
    user.pin_hash = bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()
    db.commit()
    return schemas.MessageResponse(message="PIN이 설정되었습니다")


@router.post("/pin/verify", response_model=schemas.PinVerifyResponse)
def verify_pin(
    payload: schemas.PinRequest,
    user: User = Depends(get_current_user),
):
    if not user.pin_hash:
        raise HTTPException(status_code=409, detail="PIN이 설정되지 않았습니다")
    verified = bcrypt.checkpw(payload.pin.strip().encode(), user.pin_hash.encode())
    return schemas.PinVerifyResponse(verified=verified)
