// 유닛 테스트 전용 설정 — 프로덕션 vite.config의 build/server와 격리.
// 순수 로직(lib/*) 대상. DOM/인증/라우팅 등 브라우저 의존 흐름은 Playwright E2E가 담당한다
// (vite 8 rolldown + vitest 4 조합에서 jsdom/happy-dom 환경 전역 주입이 동작하지 않아,
//  DOM 유닛 환경 대신 실브라우저 E2E로 커버 — 도구 성숙 후 재도입 가능).
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
    globals: true,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
})
