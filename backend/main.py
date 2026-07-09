"""Hooxi-CMS API — P0 기반 (auth·users·health).

Cloud Run 대응 패턴 유지: 정적 파일 경로 동적 해석 / init_db는 DB 없어도 crash 금지 /
PORT 환경변수 바인딩.
"""

import html
import mimetypes
import os
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import quote

import jwt
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

import auth
import schemas
from models import (
    Client,
    Document,
    ReportDelivery,
    SessionLocal,
    User,
    engine,
    get_db,
    init_db,
)
from routers import assets as assets_router
from routers import audit as audit_router
from routers import backups as backups_router
from routers import chat as chat_router
from routers import clients as clients_router
from routers import config as config_router
from routers import dashboard as dashboard_router
from routers import documents as documents_router
from routers import histories as histories_router
from routers import kakao as kakao_router
from routers import projects as projects_router
from routers import reports as reports_router
from routers import schedules as schedules_router
from routers import settlements as settlements_router
from routers import users as users_router
from services import storage
from services.audit_logger import AuditLogger

API_VERSION = "1.0.0"


def seed_admin():
    """사용자가 0명이면 최초 ADMIN 부트스트랩 (CR-1: DB 시드 runbook).

    DB가 없어도 앱 기동을 막지 않는다.
    """
    seed_email = os.getenv("SEED_ADMIN_EMAIL", "hooxi006@hooxipartners.com").strip().lower()
    try:
        db = SessionLocal()
        try:
            if db.query(User).count() == 0:
                admin = User(
                    email=seed_email,
                    name="관리자",
                    auth_provider="NAVER_WORKS",
                    role="ADMIN",
                    status="ACTIVE",
                )
                db.add(admin)
                db.commit()
                print(f"✓ Seeded initial ADMIN account: {seed_email}")
        finally:
            db.close()
    except Exception as exc:
        print(f"⚠ Admin seed skipped (database unavailable): {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if init_db():
        seed_admin()
    yield


app = FastAPI(
    title="Hooxi CMS API",
    description="Carbon Fleet Management System API",
    version=API_VERSION,
    lifespan=lifespan,
)

# CORS: comma-separated origins via CORS_ORIGINS env var.
# Credentials cannot be combined with a wildcard origin per the CORS spec.
cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(OperationalError)
async def db_unavailable_handler(request: Request, exc: OperationalError):
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Database constraint violated"})


# --- API v1 routers ---
API_V1_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_V1_PREFIX)
app.include_router(users_router.router, prefix=API_V1_PREFIX)
app.include_router(clients_router.router, prefix=API_V1_PREFIX)
app.include_router(histories_router.router, prefix=API_V1_PREFIX)
app.include_router(schedules_router.router, prefix=API_V1_PREFIX)
app.include_router(reports_router.router, prefix=API_V1_PREFIX)
app.include_router(documents_router.router, prefix=API_V1_PREFIX)
app.include_router(dashboard_router.router, prefix=API_V1_PREFIX)
app.include_router(assets_router.router, prefix=API_V1_PREFIX)
app.include_router(projects_router.router, prefix=API_V1_PREFIX)
app.include_router(settlements_router.router, prefix=API_V1_PREFIX)
app.include_router(kakao_router.router, prefix=API_V1_PREFIX)
app.include_router(chat_router.router, prefix=API_V1_PREFIX)
app.include_router(config_router.router, prefix=API_V1_PREFIX)
app.include_router(audit_router.router, prefix=API_V1_PREFIX)
app.include_router(backups_router.router, prefix=API_V1_PREFIX)


@app.get(f"{API_V1_PREFIX}/health", response_model=schemas.HealthResponse)
async def health_check():
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return schemas.HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        version=API_VERSION,
        database_available=db_ok,
    )


# --- 보고서 열람 페이지 (무인증 — 자족 서명 토큰, 72h 만료) ---
# 주의: API_V1_PREFIX 밖 루트 경로. SPA catch-all(/{full_path:path})보다 먼저
# 등록되어야 하므로 main.py에 직접 둔다 (라우트 매칭은 등록 순서).
_VIEW_PAGE_STYLE = (
    "body{margin:0;font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;"
    "background:#f4f5f7;color:#1f2937}"
    ".wrap{max-width:480px;margin:0 auto;padding:24px 16px}"
    ".card{background:#fff;border-radius:12px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,.08)}"
    ".brand{font-size:13px;color:#6b7280;margin-bottom:16px}"
    "h1{font-size:18px;margin:0 0 8px}"
    ".meta{font-size:14px;color:#4b5563;line-height:1.7;margin-bottom:20px}"
    ".btn{display:block;text-align:center;background:#111827;color:#fff;text-decoration:none;"
    "padding:14px 0;border-radius:8px;font-size:15px;font-weight:600}"
    ".note{font-size:12px;color:#9ca3af;margin-top:16px;line-height:1.6}"
)


def _view_page(body_html: str, title: str = "보고서 열람") -> str:
    return (
        "<!DOCTYPE html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>{0}</title><style>{1}</style></head>"
        "<body><div class=\"wrap\"><div class=\"card\">"
        "<div class=\"brand\">Hooxi Partners — Carbon Fleet</div>{2}</div></div></body></html>"
    ).format(html.escape(title), _VIEW_PAGE_STYLE, body_html)


def _view_error(status_code: int, title: str, message: str) -> HTMLResponse:
    body = "<h1>{0}</h1><div class=\"meta\">{1}</div>".format(
        html.escape(title), html.escape(message)
    )
    return HTMLResponse(content=_view_page(body, title), status_code=status_code)


def _decode_view_token(token: str):
    """열람 토큰 검증 — (payload, None) 또는 (None, 오류 HTMLResponse)."""
    try:
        payload = jwt.decode(token, auth.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None, _view_error(
            410, "열람 기간이 만료되었습니다",
            "보고서 열람 링크는 발송 후 72시간 동안 유효합니다. 담당자에게 재발송을 요청해 주세요.",
        )
    except jwt.InvalidTokenError:
        return None, _view_error(401, "유효하지 않은 링크입니다", "링크가 올바르지 않습니다. 받으신 메시지의 버튼으로 다시 접속해 주세요.")
    if payload.get("type") != "view":
        return None, _view_error(401, "유효하지 않은 링크입니다", "링크가 올바르지 않습니다. 받으신 메시지의 버튼으로 다시 접속해 주세요.")
    return payload, None


def _load_view_target(payload: dict, db: Session):
    """토큰의 doc/report 로드 — (doc, delivery) 또는 (None, None)."""
    doc = db.get(Document, payload.get("doc_id")) if payload.get("doc_id") else None
    delivery = (
        db.get(ReportDelivery, payload.get("report_id")) if payload.get("report_id") else None
    )
    return doc, delivery


@app.get("/r/{token}", response_class=HTMLResponse)
def view_report_page(token: str, db: Session = Depends(get_db)):
    """모바일 최적화 열람 페이지 — 문서명·고객사·업로드일 + 다운로드 버튼.

    열람 시 tb_audit_log(action=REPORT_VIEW) 적재 — '고객확인' 수기 체크의 참고 신호.
    """
    payload, error = _decode_view_token(token)
    if error:
        return error
    doc, delivery = _load_view_target(payload, db)
    if doc is None or delivery is None:
        return _view_error(404, "보고서를 찾을 수 없습니다", "보고서가 삭제되었거나 링크가 잘못되었습니다. 담당자에게 문의해 주세요.")

    client = db.get(Client, delivery.client_id) if delivery.client_id else None

    # 열람 추적 (REPORT_VIEW) — actor는 발송 담당자 기준(무인증 열람, tb_user FK 제약)
    actor_id = delivery.manager_id or doc.uploaded_by
    if actor_id:
        AuditLogger.report_view(db, actor_id, delivery.report_id)
        db.commit()
    # 다운로드: GCS는 서명 URL, 로컬 저장소는 토큰 재검증 스트림 엔드포인트
    if doc.file_url.startswith("gs://"):
        download_url = storage.get_url(doc.file_url, expires_seconds=3600)
    else:
        download_url = "/r/{0}/file".format(token)

    uploaded = doc.created_at.strftime("%Y-%m-%d") if doc.created_at else "-"
    body = (
        "<h1>{title}</h1>"
        "<div class=\"meta\">고객사: {client}<br>보고 기간: {period} · {rtype}<br>업로드일: {uploaded}</div>"
        "<a class=\"btn\" href=\"{url}\">보고서 다운로드</a>"
        "<div class=\"note\">본 링크는 발송 후 72시간 동안 유효합니다.<br>"
        "문의 사항은 담당자에게 회신해 주세요.</div>"
    ).format(
        title=html.escape(doc.title or "보고서"),
        client=html.escape(client.company_name if client else "-"),
        period=html.escape(delivery.period or "-"),
        rtype=html.escape(delivery.report_type or "-"),
        uploaded=uploaded,
        url=html.escape(download_url or "#"),
    )
    return HTMLResponse(content=_view_page(body, doc.title or "보고서 열람"))


@app.get("/r/{token}/file")
def view_report_file(token: str, db: Session = Depends(get_db)):
    """로컬 저장소 파일 스트림 — 토큰 재검증(무인증 다운로드 경로, 로컬 폴백 전용)."""
    payload, error = _decode_view_token(token)
    if error:
        return error
    doc, delivery = _load_view_target(payload, db)
    if doc is None or delivery is None:
        return JSONResponse(status_code=404, content={"detail": "보고서를 찾을 수 없습니다"})

    content = storage.read_file(doc.file_url)
    if content is None:
        return JSONResponse(status_code=404, content={"detail": "보고서 파일을 저장소에서 읽을 수 없습니다"})

    filename = os.path.basename(doc.file_url) or "report"
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''{0}".format(quote(filename))
        },
    )


# --- Static files (built React app) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

possible_paths = [
    "/app/dist",  # Docker/Cloud Run environment
    os.path.join(os.path.dirname(BASE_DIR), "frontend", "dist"),  # Local: ../frontend/dist
    os.path.join(BASE_DIR, "dist"),  # Alternative local location
]

dist_path = next((p for p in possible_paths if os.path.exists(p)), None)

if dist_path:
    app.mount("/static", StaticFiles(directory=dist_path), name="static")
    # Vite emits <script src="./assets/..."> which resolves to /assets at the root
    assets_path = os.path.join(dist_path, "assets")
    if os.path.exists(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="assets")
    print(f"✓ Serving static files from: {dist_path}")
else:
    print("⚠ No dist folder found — API only. Run 'npm run build' in frontend directory.")


@app.get("/")
async def root():
    """Serve React app for frontend"""
    if dist_path:
        index_path = os.path.join(dist_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)

    # Fallback to API response if no static files found
    return {"Hello": "World", "API": f"Hooxi CMS v{API_VERSION}"}


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """SPA 딥링크(/dashboard, /clients/... 등) → index.html.

    API 경로는 라우터가 먼저 매칭되므로 여기 도달하면 진짜 404.
    """
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    if dist_path:
        index_path = os.path.join(dist_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"detail": "Not Found"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
