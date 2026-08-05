"""프로덕션 기동 가드 — 기본 JWT_SECRET + dev-login 비활성이면 기동 차단."""

import pytest

import auth
import main


def test_guard_blocks_default_secret_in_prod(monkeypatch):
    # 운영 추정: 기본 시크릿 + dev-login 꺼짐 → 차단
    monkeypatch.setattr(auth, "JWT_SECRET", auth._DEFAULT_JWT_SECRET)
    monkeypatch.setenv("ENABLE_DEV_LOGIN", "false")
    with pytest.raises(RuntimeError):
        main.require_secure_jwt_secret()


def test_guard_blocks_default_secret_even_with_dev_login(monkeypatch):
    # 하드닝(H2): dev-login이 켜져 있어도 기본 시크릿은 항상 차단 — '기본키+dev-login' 조합 봉쇄
    monkeypatch.setattr(auth, "JWT_SECRET", auth._DEFAULT_JWT_SECRET)
    monkeypatch.setenv("ENABLE_DEV_LOGIN", "true")
    with pytest.raises(RuntimeError):
        main.require_secure_jwt_secret()


def test_guard_allows_custom_secret(monkeypatch):
    # 운영이어도 커스텀 시크릿이면 허용
    monkeypatch.setattr(auth, "JWT_SECRET", "a-real-strong-secret")
    monkeypatch.setenv("ENABLE_DEV_LOGIN", "false")
    main.require_secure_jwt_secret()  # 예외 없음
