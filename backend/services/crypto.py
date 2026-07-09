"""자산 인증정보 암호화 — SCR-04 (P2).

- 알고리즘: AES-256-GCM (`cryptography` 라이브러리 AESGCM)
- 키: 환경변수 `ASSET_ENC_KEY` (base64 인코딩된 32바이트)
- 저장 포맷: base64( nonce(12바이트) + ciphertext+tag )
- 키 미설정 시: 암호화가 필요한 작업(인증정보 저장·reveal)만 503 —
  그 외 CRUD·앱 기동은 정상 동작해야 한다.
"""

import base64
import os
from typing import Optional

from fastapi import HTTPException

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover — requirements.txt에 포함
    AESGCM = None

ENV_KEY_NAME = "ASSET_ENC_KEY"
_NONCE_SIZE = 12

_KEY_MISSING_MESSAGE = (
    "암호화 키(ASSET_ENC_KEY)가 설정되지 않아 인증정보를 처리할 수 없습니다. "
    "base64 인코딩된 32바이트 키를 환경변수로 설정하세요."
)


def _load_key() -> Optional[bytes]:
    """환경변수에서 키를 매 호출 시점에 로드 — 설정 여부가 런타임에 바뀔 수 있다."""
    raw = os.getenv(ENV_KEY_NAME, "").strip()
    if not raw:
        return None
    try:
        key = base64.b64decode(raw)
    except Exception:
        return None
    if len(key) != 32:
        return None
    return key


def encryption_available() -> bool:
    """암호화 가능 여부 — 라이브러리 존재 + 유효한 32바이트 키."""
    return AESGCM is not None and _load_key() is not None


def _require_key() -> bytes:
    if AESGCM is None:
        raise HTTPException(
            status_code=503,
            detail="cryptography 라이브러리가 설치되지 않아 인증정보를 처리할 수 없습니다",
        )
    key = _load_key()
    if key is None:
        raise HTTPException(status_code=503, detail=_KEY_MISSING_MESSAGE)
    return key


def encrypt(plaintext: str) -> str:
    """평문 인증정보 → AES-256-GCM 암호문(base64). 키 미설정 시 503."""
    key = _require_key()
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token: str) -> str:
    """암호문(base64) → 평문. 키 미설정 시 503, 키 불일치·손상 시 500."""
    key = _require_key()
    try:
        blob = base64.b64decode(token)
        nonce, ciphertext = blob[:_NONCE_SIZE], blob[_NONCE_SIZE:]
        return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="인증정보 복호화에 실패했습니다 — 암호화 키가 변경되었거나 데이터가 손상되었습니다",
        )
