"""Hooxi-CMS API — P0 기반 (auth·users·health).

Cloud Run 대응 패턴 유지: 정적 파일 경로 동적 해석 / init_db는 DB 없어도 crash 금지 /
PORT 환경변수 바인딩.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

import auth
import schemas
from models import SessionLocal, User, engine, init_db
from routers import clients as clients_router
from routers import dashboard as dashboard_router
from routers import documents as documents_router
from routers import histories as histories_router
from routers import reports as reports_router
from routers import schedules as schedules_router
from routers import users as users_router

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
