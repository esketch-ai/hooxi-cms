import { defineConfig } from '@playwright/test'

// 백엔드 python 실행기 — 기본 python3(백엔드 deps 설치 전제). 환경별 override 가능(E2E_PYTHON).
const PY = process.env.E2E_PYTHON || 'python3'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: false,
  use: { baseURL: 'http://localhost:8000', trace: 'on-first-retry' },
  // 프로덕션 충실: 프론트 빌드 → 백엔드가 dist 서빙(단일 포트). 격리 SQLite + 미설정 외부연동.
  webServer: {
    command: `npm run build && rm -f ../backend/e2e.db && cd ../backend && DATABASE_URL=sqlite:///./e2e.db ENABLE_DEV_LOGIN=true JWT_SECRET=e2e-secret-key-not-the-default-value SEED_ADMIN_EMAIL=hooxi006@hooxipartners.com APP_BASE_URL=http://localhost:8000 CORS_ORIGINS=http://localhost:8000 ${PY} -m uvicorn main:app --host 127.0.0.1 --port 8000`,
    url: 'http://localhost:8000/api/v1/health',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
