"""P1 스모크 테스트 설정 — 임시 SQLite + TestClient.

주의: models.py는 import 시점에 engine을 만들므로, 환경변수 준비와 엔진 교체를
어떤 테스트 모듈보다 먼저(conftest import 시) 수행한다.
"""

import os

# --- 환경 준비 (import 순서 중요) ---
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/test_p1.db")
os.environ.setdefault("ENABLE_DEV_LOGIN", "true")
os.environ.setdefault("JWT_SECRET", "test")
os.environ["UPLOAD_DIR"] = "/tmp/test_p1_uploads"
os.environ.pop("GMAIL_SENDER", None)
os.environ.pop("GMAIL_APP_PASSWORD", None)
os.environ.pop("GCS_BUCKET", None)
# 카카오 연동(P3) — 로컬 환경변수 격리 (미설정 상태에서 테스트 시작)
for _key in (
    "SOLAPI_API_KEY", "SOLAPI_API_SECRET", "SOLAPI_SENDER", "KAKAO_PF_ID",
    "KAKAO_TEMPLATE_REPORT", "KAKAO_TEMPLATE_REPLY", "KAKAO_BOT_ID",
    "KAKAO_EVENT_API_KEY", "KAKAO_WEBHOOK_SECRET", "KAKAO_EVENT_NAME", "APP_BASE_URL",
):
    os.environ.pop(_key, None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import models  # noqa: E402

# SQLite + TestClient 스레드 조합 대응: check_same_thread=False, 커넥션 재사용 금지
_test_engine = create_engine(
    os.environ["DATABASE_URL"],
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)
models.engine.dispose()
models.engine = _test_engine
models.SessionLocal.configure(bind=_test_engine)

import main  # noqa: E402

main.engine = _test_engine


@pytest.fixture(scope="session")
def client():
    models.Base.metadata.drop_all(bind=_test_engine)
    models.Base.metadata.create_all(bind=_test_engine)

    db = models.SessionLocal()
    try:
        db.add_all(
            [
                models.User(
                    user_id="u-admin", email="admin@hooxipartners.com",
                    name="관리자", role="ADMIN", status="ACTIVE",
                ),
                models.User(
                    user_id="u-manager", email="manager@hooxipartners.com",
                    name="팀장", role="MANAGER", status="ACTIVE",
                ),
                models.User(
                    user_id="u-staff", email="staff@hooxipartners.com",
                    name="실무자", role="STAFF", status="ACTIVE",
                ),
                models.User(
                    user_id="u-pending", email="pending@hooxipartners.com",
                    name="대기자", role="STAFF", status="PENDING",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    with TestClient(main.app) as c:
        yield c


def _login(client, email):
    resp = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert resp.status_code == 200, resp.text
    return {"Authorization": "Bearer {0}".format(resp.json()["access_token"])}


@pytest.fixture(scope="session")
def admin_headers(client):
    return _login(client, "admin@hooxipartners.com")


@pytest.fixture(scope="session")
def staff_headers(client):
    return _login(client, "staff@hooxipartners.com")
