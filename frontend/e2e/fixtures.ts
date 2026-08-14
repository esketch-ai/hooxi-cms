import { test as base, expect, type APIRequestContext } from '@playwright/test'

// ── E2E 브라우저 인증 헬퍼 ──────────────────────────────────────────────
// 앱은 토큰을 localStorage(hooxi_access_token/hooxi_refresh_token)에 저장하고
// (src/lib/api/client.ts), 부팅 시 그 access로 /users/me를 조회해 인증 상태를 만든다
// (src/app/AuthProvider.tsx). 또한 RequireAuth(src/app/router.tsx)는 pin_set=true가
// 아니면 /login으로 튕긴다. 시드 ADMIN은 PIN 미설정이므로, dev-login 토큰으로 PIN을
// 한 번 설정(멱등)해 pin_set을 확보한 뒤 토큰을 브라우저에 주입한다.

export const ADMIN_EMAIL = 'hooxi006@hooxipartners.com'

const ACCESS_KEY = 'hooxi_access_token'
const REFRESH_KEY = 'hooxi_refresh_token'
const E2E_PIN = '482913' // 4~6자리 숫자 규칙 충족 (auth.set_pin)

/** dev-login으로 ADMIN 토큰 발급 + PIN 설정(pin_set=true 확보). */
async function issueAdminSession(request: APIRequestContext) {
  const res = await request.post('/api/v1/auth/dev-login', {
    data: { email: ADMIN_EMAIL },
  })
  expect(res.ok(), 'dev-login이 성공해야 함').toBeTruthy()
  const { access_token, refresh_token } = await res.json()
  expect(access_token, 'access_token 발급').toBeTruthy()

  // pin_set=false면 RequireAuth가 /login으로 리다이렉트 → PIN 설정으로 pin_set=true (멱등)
  const pinRes = await request.post('/api/v1/auth/pin', {
    headers: { Authorization: `Bearer ${access_token}` },
    data: { pin: E2E_PIN },
  })
  expect(pinRes.ok(), 'PIN 설정이 성공해야 함').toBeTruthy()

  return { access_token, refresh_token }
}

// ADMIN 인증 상태로 진입한 page를 제공하는 확장 테스트.
export const test = base.extend({
  page: async ({ page, context, request }, use) => {
    const { access_token, refresh_token } = await issueAdminSession(request)
    // 앱이 읽는 localStorage 키에 토큰을 주입 — 이후 모든 navigation에서 인증 상태로 부팅
    await context.addInitScript(
      ({ access, refresh, accessKey, refreshKey }) => {
        localStorage.setItem(accessKey, access)
        localStorage.setItem(refreshKey, refresh)
      },
      {
        access: access_token,
        refresh: refresh_token,
        accessKey: ACCESS_KEY,
        refreshKey: REFRESH_KEY,
      },
    )
    await use(page)
  },
})

export { expect }
