import { expect, test } from '@playwright/test'

// 스택 스모크 — 프론트 빌드→백엔드 dist 서빙→브라우저 SPA 로드→dev-login 인증까지 한 번에 검증.
test('앱·백엔드 기동 + 로그인 화면 렌더 + dev-login 인증', async ({ page, request }) => {
  // 1) 백엔드 health 200
  const health = await request.get('/api/v1/health')
  expect(health.ok()).toBeTruthy()

  // 2) SPA 로그인 화면이 렌더된다(백엔드가 dist를 정적 서빙 — SPA 폴백 포함)
  await page.goto('/login')
  await expect(page.getByAltText('Hooxi Partners')).toBeVisible()

  // 3) dev-login 백엔드 동작(빈 DB에 자동 시드된 ADMIN으로 토큰 발급)
  const res = await request.post('/api/v1/auth/dev-login', {
    data: { email: 'hooxi006@hooxipartners.com' },
  })
  expect(res.ok()).toBeTruthy()
  expect((await res.json()).access_token).toBeTruthy()
})
