"""연동 설정 관리 — DB(tb_config) 저장값 우선 + 환경변수 폴백 (SCR-14 연동 탭).

- 단일 원천 REGISTRY: 연동별 필드 정의(시크릿 여부·필수 여부·기본값·한국어 라벨).
- 저장: tb_config key "integration.{name}", value = JSON 객체.
  시크릿 필드는 "enc:" + AES-256-GCM 암호문(services/crypto.py — ASSET_ENC_KEY),
  일반 필드는 평문. 키 미설정 시 시크릿 저장은 503 (crypto._require_key 게이트).
- resolve(env_key): DB 저장값 → os.getenv → REGISTRY 기본값 순으로 해석.
  DB 조회 결과는 모듈 레벨 캐시에 보관하고, 저장 시 bump_version()으로 무효화.
  env 폴백은 항상 호출 시점에 읽는다(테스트 monkeypatch·런타임 변경 대응).
- 시크릿 값은 status()/이력/감사 로그 어디에도 원문을 남기지 않는다 (R2-E6).
"""

import json
import os
import threading
from typing import Dict, List, Optional

from fastapi import HTTPException

import models
from models import Config
from services import crypto

CONFIG_KEY_PREFIX = "integration."
SECRET_PREFIX = "enc:"
MASK = "***"


class IntegrationField:
    """연동 설정 필드 정의 — REGISTRY 전용 경량 값 객체."""

    __slots__ = ("key", "label", "secret", "required", "default")

    def __init__(
        self,
        key: str,
        label: str,
        secret: bool = False,
        required: bool = True,
        default: Optional[str] = None,
    ):
        self.key = key
        self.label = label
        self.secret = secret
        self.required = required
        self.default = default


# 연동·필드 정의 — 단일 원천. 필드 추가·변경은 여기서만.
REGISTRY: Dict[str, dict] = {
    "dropbox": {
        "label": "Dropbox 저장소",
        "fields": [
            IntegrationField("DROPBOX_APP_KEY", "앱 키"),
            IntegrationField("DROPBOX_APP_SECRET", "앱 시크릿", secret=True),
            IntegrationField("DROPBOX_REFRESH_TOKEN", "리프레시 토큰", secret=True),
            IntegrationField(
                "DROPBOX_ROOT", "루트 폴더", required=False, default="/Hooxi-CMS"
            ),
        ],
    },
    "solapi": {
        "label": "카카오 알림톡 (SOLAPI)",
        "fields": [
            IntegrationField("SOLAPI_API_KEY", "API 키"),
            IntegrationField("SOLAPI_API_SECRET", "API 시크릿", secret=True),
            IntegrationField("KAKAO_PF_ID", "발신프로필 ID"),
            IntegrationField("KAKAO_TEMPLATE_REPORT", "보고서 도착 템플릿", required=False),
            IntegrationField("KAKAO_TEMPLATE_REPLY", "답변 알림 템플릿", required=False),
            IntegrationField("SOLAPI_SENDER", "등록 발신번호(문자 폴백)", required=False),
        ],
    },
    "kakao_bot": {
        "label": "카카오 챗봇 (오픈빌더)",
        "fields": [
            IntegrationField("KAKAO_BOT_ID", "봇 ID"),
            IntegrationField("KAKAO_EVENT_API_KEY", "Event API 키", secret=True),
            IntegrationField("KAKAO_WEBHOOK_SECRET", "웹훅 시크릿", secret=True),
            IntegrationField(
                "KAKAO_EVENT_NAME", "답변 이벤트명", required=False, default="staff_reply"
            ),
        ],
    },
    "gmail": {
        "label": "Gmail 발송 계정",
        "fields": [
            IntegrationField("GMAIL_SENDER", "발신 이메일"),
            IntegrationField("GMAIL_APP_PASSWORD", "앱 비밀번호", secret=True),
        ],
    },
    "naver_works": {
        "label": "네이버웍스 SSO",
        "fields": [
            IntegrationField("NW_CLIENT_ID", "클라이언트 ID"),
            IntegrationField("NW_CLIENT_SECRET", "클라이언트 시크릿", secret=True),
            IntegrationField("NW_REDIRECT_URI", "리다이렉트 URI"),
        ],
    },
}

# env_key → (연동 이름, 필드) 역인덱스
_FIELD_INDEX: Dict[str, tuple] = {
    field.key: (name, field)
    for name, spec in REGISTRY.items()
    for field in spec["fields"]
}

# --- 모듈 레벨 캐시 — 저장(bump_version) 시 무효화 ---
_lock = threading.Lock()
_version = 0
_cache: Dict[str, Dict[str, str]] = {}  # name → 복호화된 DB 저장값


def get_version() -> int:
    """현재 설정 버전 — dropbox_storage 등 싱글턴 재생성 판단용."""
    return _version


def bump_version() -> None:
    """설정 저장 후 호출 — 캐시 전체 무효화 + 버전 증가."""
    global _version
    with _lock:
        _version += 1
        _cache.clear()


def config_key(name: str) -> str:
    return CONFIG_KEY_PREFIX + name


def field_for(env_key: str) -> Optional[IntegrationField]:
    entry = _FIELD_INDEX.get(env_key)
    return entry[1] if entry else None


def require_encryption_available() -> None:
    """시크릿 저장 전 게이트 — ASSET_ENC_KEY 미설정 시 503 (crypto 규약 미러)."""
    if not crypto.encryption_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "암호화 키(ASSET_ENC_KEY)가 설정되지 않아 연동 시크릿을 저장할 수 없습니다. "
                "base64 인코딩된 32바이트 키를 환경변수로 설정하세요."
            ),
        )


def _load_db_values(name: str) -> Dict[str, str]:
    """연동의 DB 저장값 로드(+복호화) — 캐시 우선, DB 세션은 자체 오픈(짧게).

    - DB 접근 실패: 캐시하지 않고 빈 dict(→ env 폴백) — 무중단 원칙.
    - 시크릿 복호화 실패(키 미설정·변경): 해당 필드만 건너뜀(→ env 폴백).
    """
    cached = _cache.get(name)
    if cached is not None:
        return cached

    try:
        db = models.SessionLocal()
        try:
            row = db.get(Config, config_key(name))
            raw = row.config_value if row is not None else None
        finally:
            db.close()
    except Exception:
        return {}

    values: Dict[str, str] = {}
    if raw:
        try:
            stored = json.loads(raw)
        except (ValueError, TypeError):
            stored = None
        if isinstance(stored, dict):
            for key, value in stored.items():
                if not isinstance(value, str) or not value:
                    continue
                if value.startswith(SECRET_PREFIX):
                    try:
                        values[key] = crypto.decrypt(value[len(SECRET_PREFIX):])
                    except HTTPException:
                        continue
                else:
                    values[key] = value

    with _lock:
        _cache[name] = values
    return values


def resolve(env_key: str) -> Optional[str]:
    """연동 설정값 해석 — DB 저장값 우선, 없으면 환경변수, 마지막으로 기본값."""
    entry = _FIELD_INDEX.get(env_key)
    if entry is None:
        return os.getenv(env_key)
    name, field = entry
    db_value = _load_db_values(name).get(env_key)
    if db_value:
        return db_value
    env_value = os.getenv(env_key)
    if env_value:
        return env_value
    return field.default


def status(name: str) -> Dict[str, dict]:
    """필드별 설정 상태 — {key: {configured, source}}. 시크릿 값 자체는 절대 미포함."""
    spec = REGISTRY[name]
    db_values = _load_db_values(name)
    result: Dict[str, dict] = {}
    for field in spec["fields"]:
        if db_values.get(field.key):
            source: Optional[str] = "db"
        elif os.getenv(field.key):
            source = "env"
        else:
            source = None
        result[field.key] = {"configured": source is not None, "source": source}
    return result


# ---------------------------------------------------------------------------
# 저장 — 라우터(PUT /integrations/{name})가 사용. 커밋·이력·감사·bump는 호출부 책임.
# ---------------------------------------------------------------------------
def masked_stored_json(name: str, stored: Dict[str, str]) -> str:
    """저장 포맷(dict) → 이력 기록용 JSON — 시크릿 필드는 '***' 마스킹 (R2-E6)."""
    masked = {}
    for key, value in stored.items():
        field = field_for(key)
        masked[key] = MASK if (field is not None and field.secret) else value
    return json.dumps(masked, ensure_ascii=False, sort_keys=True)


def apply_updates(db, name: str, updates: Dict[str, Optional[str]], actor_id: str):
    """전달된 키만 갱신(null/빈 문자열=삭제, 미전달=유지) — 시크릿은 암호화 저장.

    반환: (row, old_masked_json|None, new_masked_json, changed_keys)
    """
    spec = REGISTRY[name]
    unknown = [k for k in updates if field_for(k) is None or _FIELD_INDEX[k][0] != name]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail="'{0}' 연동에 없는 설정 키입니다: {1}".format(name, ", ".join(sorted(unknown))),
        )

    key = config_key(name)
    row = db.get(Config, key)
    old_raw = row.config_value if row is not None else None
    try:
        stored = json.loads(old_raw) if old_raw else {}
    except (ValueError, TypeError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    old_masked = masked_stored_json(name, stored) if old_raw else None

    # 시크릿 신규 저장이 포함되면 암호화 가능 여부를 먼저 게이트 (부분 저장 방지)
    if any(
        field_for(k).secret and isinstance(v, str) and v.strip()
        for k, v in updates.items()
    ):
        require_encryption_available()

    changed_keys: List[str] = []
    for env_key, value in updates.items():
        field = field_for(env_key)
        if value is None or not str(value).strip():
            if env_key in stored:
                stored.pop(env_key)
                changed_keys.append(env_key)
            continue
        value = str(value).strip()
        stored[env_key] = (
            SECRET_PREFIX + crypto.encrypt(value) if field.secret else value
        )
        changed_keys.append(env_key)

    new_raw = json.dumps(stored, ensure_ascii=False, sort_keys=True)
    if row is None:
        row = Config(config_key=key, description="{0} 연동 설정".format(spec["label"]))
        db.add(row)
    row.config_value = new_raw
    row.updated_by = actor_id

    return row, old_masked, masked_stored_json(name, stored), sorted(changed_keys)
