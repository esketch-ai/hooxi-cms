"""카카오 비즈니스 채널 발송 모듈 — 알림톡(SOLAPI) + 오픈빌더 Event API.

- 알림톡(발신): SOLAPI REST — HMAC-SHA256 서명 인증(date+salt).
  env: SOLAPI_API_KEY / SOLAPI_API_SECRET / KAKAO_PF_ID(발신프로필)
       KAKAO_TEMPLATE_REPORT(보고서 도착) / KAKAO_TEMPLATE_REPLY(답변 알림)
- Event API(답변 통지): 오픈빌더 봇 이벤트 — 채널 친구 한정(15원/건).
  env: KAKAO_BOT_ID / KAKAO_EVENT_API_KEY
- 공통: KAKAO_WEBHOOK_SECRET(웹훅 시크릿) / APP_BASE_URL(열람 링크 베이스)

email_service.py의 is_configured 게이트 패턴을 미러 — 미설정 시 KakaoConfigError를
던지고 호출부가 503 한국어 메시지로 변환한다.
"""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

SOLAPI_SEND_URL = "https://api.solapi.com/messages/v4/send"
EVENT_API_URL = "https://bot-api.kakao.com/v2/bots/{bot_id}/talk"

REQUEST_TIMEOUT = 10.0  # 초 — 오픈빌더 스킬 5초 제한과 별개(발신 전용 경로)


class KakaoConfigError(RuntimeError):
    """카카오 연동 환경변수 미설정."""


class KakaoSendError(RuntimeError):
    """카카오 발송 실패 — API 오류 응답."""


# ---------------------------------------------------------------------------
# 설정 게이트 (email_service.is_configured 패턴)
# ---------------------------------------------------------------------------
def is_configured_alimtalk() -> bool:
    """SOLAPI 알림톡 발송 가능 여부."""
    return bool(
        os.getenv("SOLAPI_API_KEY")
        and os.getenv("SOLAPI_API_SECRET")
        and os.getenv("KAKAO_PF_ID")
    )


def is_configured_event() -> bool:
    """오픈빌더 Event API 발송 가능 여부."""
    return bool(os.getenv("KAKAO_BOT_ID") and os.getenv("KAKAO_EVENT_API_KEY"))


def webhook_secret() -> Optional[str]:
    """오픈빌더 스킬 웹훅 검증용 시크릿 — 미설정 시 None(웹훅 비활성)."""
    return os.getenv("KAKAO_WEBHOOK_SECRET") or None


def app_base_url() -> str:
    """열람 링크 베이스 URL — 끝 슬래시 제거."""
    return (os.getenv("APP_BASE_URL") or "").rstrip("/")


# ---------------------------------------------------------------------------
# SOLAPI 알림톡 — HMAC-SHA256 서명 인증
# ---------------------------------------------------------------------------
def _solapi_auth_header(api_key: str, api_secret: str) -> str:
    """SOLAPI HMAC-SHA256 인증 헤더 생성.

    signature = HMAC-SHA256(api_secret, date + salt)
    date: ISO 8601(UTC), salt: 12~64자 랜덤 문자열.
    """
    date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    salt = secrets.token_hex(16)
    signature = hmac.new(
        api_secret.encode(), (date + salt).encode(), hashlib.sha256
    ).hexdigest()
    return (
        "HMAC-SHA256 apiKey={0}, date={1}, salt={2}, signature={3}".format(
            api_key, date, salt, signature
        )
    )


def send_alimtalk(
    to: str,
    template_code: str,
    variables: Optional[Dict[str, str]] = None,
    buttons: Optional[List[dict]] = None,
) -> dict:
    """알림톡 1건 발송 — SOLAPI POST /messages/v4/send.

    - to: 수신자 휴대폰 번호(하이픈 무관 — 숫자만 추출해 전달)
    - template_code: 승인된 알림톡 템플릿 ID
    - variables: 템플릿 변수 — {"#{고객사명}": "...", ...} 형태로 변환해 전달
    - buttons: SOLAPI kakaoOptions.buttons 규격(웹링크 등) — 템플릿과 일치해야 함
    실패 시 KakaoSendError 전파(호출부가 send_log FAIL 기록).
    """
    api_key = os.getenv("SOLAPI_API_KEY")
    api_secret = os.getenv("SOLAPI_API_SECRET")
    pf_id = os.getenv("KAKAO_PF_ID")
    if not (api_key and api_secret and pf_id):
        raise KakaoConfigError(
            "카카오 알림톡이 설정되지 않았습니다. "
            "SOLAPI_API_KEY / SOLAPI_API_SECRET / KAKAO_PF_ID 환경변수를 설정하세요. "
            "(SOLAPI 발신프로필 연동 + 템플릿 승인 필요)"
        )

    kakao_options = {
        "pfId": pf_id,
        "templateId": template_code,
        "variables": {
            ("#{{{0}}}".format(k) if not k.startswith("#{") else k): str(v)
            for k, v in (variables or {}).items()
        },
    }
    if buttons:
        kakao_options["buttons"] = buttons

    payload = {
        "message": {
            "to": "".join(ch for ch in to if ch.isdigit()),
            "kakaoOptions": kakao_options,
        }
    }
    sender = os.getenv("SOLAPI_SENDER")  # 선택 — 등록 발신번호(문자 폴백용)
    if sender:
        payload["message"]["from"] = "".join(ch for ch in sender if ch.isdigit())

    headers = {"Authorization": _solapi_auth_header(api_key, api_secret)}
    resp = httpx.post(SOLAPI_SEND_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
    if resp.status_code >= 400:
        raise KakaoSendError(
            "알림톡 발송 실패 (SOLAPI {0}): {1}".format(resp.status_code, resp.text[:300])
        )
    return resp.json()


# ---------------------------------------------------------------------------
# 오픈빌더 Event API — 직원 답변 통지(채널 친구 한정)
# ---------------------------------------------------------------------------
def send_event(kakao_user_key: str, event_name: str, params: Optional[dict] = None) -> dict:
    """오픈빌더 이벤트 발송 — POST https://bot-api.kakao.com/v2/bots/{bot_id}/talk.

    Authorization: KakaoAK {event_api_key}. 비친구 등 발송 불가 시 KakaoSendError 전파.
    """
    bot_id = os.getenv("KAKAO_BOT_ID")
    event_api_key = os.getenv("KAKAO_EVENT_API_KEY")
    if not (bot_id and event_api_key):
        raise KakaoConfigError(
            "카카오 Event API가 설정되지 않았습니다. "
            "KAKAO_BOT_ID / KAKAO_EVENT_API_KEY 환경변수를 설정하세요. "
            "(오픈빌더 이벤트 블록 등록 + 월렛 충전 필요)"
        )

    payload = {
        "event": {"name": event_name},
        "user": [{"type": "botUserKey", "id": kakao_user_key}],
        "params": params or {},
    }
    headers = {"Authorization": "KakaoAK {0}".format(event_api_key)}
    resp = httpx.post(
        EVENT_API_URL.format(bot_id=bot_id),
        json=payload,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise KakaoSendError(
            "Event API 발송 실패 ({0}): {1}".format(resp.status_code, resp.text[:300])
        )
    return resp.json()
