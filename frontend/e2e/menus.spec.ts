import { expect, test } from './fixtures'

// 메뉴별 핵심 흐름 E2E — ADMIN 인증 상태(fixtures)에서 각 내부 LNB 메뉴를 순회한다.
// 검증 원칙: 빈 SQLite라 데이터는 없을 수 있으므로 "데이터"가 아니라 "화면 골격"
// (PageHeader h1 제목/안정적 랜드마크)과 "로그인으로 튕기지 않음"을 확인한다.
// 셀렉터는 role/label 기반(getByRole/getByText) 우선.

// 인증 주입이 실제로 보호 라우트를 렌더하는지 선검증 (실패 시 원인 조기 규명).
test('인증 주입 — 보호 라우트가 /login으로 튕기지 않고 렌더', async ({ page }) => {
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/dashboard/)
  await expect(page).not.toHaveURL(/\/login/)
  await expect(page.getByRole('heading', { name: '통합 현황판' })).toBeVisible()
})

// path → 그 화면의 안정적 헤딩(PageHeader가 렌더하는 h1) 제목.
const MENUS: { path: string; heading: string }[] = [
  { path: '/dashboard', heading: '통합 현황판' },
  { path: '/observe', heading: '경영 관찰' },
  { path: '/issues', heading: '이슈 보드' },
  { path: '/calendar', heading: '일정 캘린더' },
  { path: '/clients', heading: '고객사 마스터' },
  { path: '/buyers', heading: '매수자 마스터' },
  { path: '/assets', heading: '자산·연동 마스터' },
  { path: '/accounts', heading: '계정 점검' },
  { path: '/histories', heading: '영업 활동 이력' },
  { path: '/reports', heading: '월간 보고서 발송 관리' },
  { path: '/documents', heading: '문서 아카이브' },
  { path: '/projects', heading: '감축 사업 관리' },
  { path: '/asset-vehicles', heading: '전기버스 자산' },
  { path: '/finance-ledger', heading: '재무 원장' },
  { path: '/portal-accounts', heading: '외부 포털 계정' },
  { path: '/settings', heading: '환경 설정' },
  { path: '/guide', heading: '사용자 가이드' },
]

for (const { path, heading } of MENUS) {
  test(`메뉴 ${path} — 로그인 리다이렉트 없이 화면 골격 렌더`, async ({ page }) => {
    await page.goto(path)
    // 보호 라우트가 로그인으로 튕기지 않음
    await expect(page).not.toHaveURL(/\/login/)
    await expect(page).toHaveURL(new RegExp(path.replace('/', '\\/')))
    // 화면의 안정적 헤딩(빈 상태여도 존재)
    await expect(page.getByRole('heading', { name: heading })).toBeVisible()
  })
}

// /chat — PageHeader가 없는 2단 레이아웃. 우측 빈 상태 안내 문구로 골격 확인.
test('메뉴 /chat — 상담 관제 빈 상태 렌더', async ({ page }) => {
  await page.goto('/chat')
  await expect(page).not.toHaveURL(/\/login/)
  await expect(page.getByText('좌측 목록에서 상담을 선택하세요')).toBeVisible()
})

// ── 대표 상호작용(가벼운 것만) ──────────────────────────────────────────

// /clients — 신규 등록 진입점 노출(데스크톱 뷰포트에서 버튼 visible)
test('/clients — 신규 고객사 등록 버튼 노출', async ({ page }) => {
  await page.goto('/clients')
  await expect(page.getByRole('button', { name: '신규 고객사 등록' })).toBeVisible()
})

// /guide — 허브에서 온보딩 토픽으로 이동(카드→토픽 라우팅)
test('/guide — 허브 온보딩 카드 클릭 시 토픽으로 이동', async ({ page }) => {
  await page.goto('/guide')
  await expect(page.getByRole('heading', { name: '사용자 가이드' })).toBeVisible()
  // 온보딩 트랙 첫 스텝의 '가이드 보기' → /guide/start
  await page.getByRole('link', { name: '가이드 보기' }).first().click()
  await expect(page).toHaveURL(/\/guide\/[^/]+/)
  await expect(page.getByRole('heading', { level: 2 }).first()).toBeVisible()
})

// /finance-ledger — 데이터 없이도 렌더되는 시세 배너(골격) 확인
test('/finance-ledger — 매출단가 시세 배너 렌더', async ({ page }) => {
  await page.goto('/finance-ledger')
  await expect(page.getByText('현재 매출단가 시세')).toBeVisible()
})

// OBSERVER 역할 격리는 이번 범위 밖(내부 ADMIN 흐름에 집중).
