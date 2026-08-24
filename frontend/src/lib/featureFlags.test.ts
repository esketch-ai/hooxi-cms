import { describe, expect, it } from 'vitest'
import {
  FINANCE_HIDDEN_PATHS,
  PORTAL_FEATURES,
  filterFinanceRoutes,
  includePortalRoutes,
  isFinanceHiddenPath,
} from './featureFlags'

// 재무 은닉 게이팅 순수 로직 — flag를 인자로 받아 결정적으로 검증(빌드 env 무관).
// portalEnabled 기본값은 빌드 env(테스트 env는 FINANCE on → PORTAL true)라 명시 인자로 고정.
describe('isFinanceHiddenPath', () => {
  it('은닉 전 경로는 정확 매칭 시 true(포털 OFF)', () => {
    for (const p of FINANCE_HIDDEN_PATHS) expect(isFinanceHiddenPath(p, false)).toBe(true)
  })
  it('포털 ON이면 /portal-accounts만 은닉 제외', () => {
    expect(isFinanceHiddenPath('/portal-accounts', true)).toBe(false)
    for (const p of FINANCE_HIDDEN_PATHS.filter((x) => x !== '/portal-accounts'))
      expect(isFinanceHiddenPath(p, true)).toBe(true)
  })
  it('은닉 경로의 하위 경로(startsWith 경계)도 true', () => {
    expect(isFinanceHiddenPath('/finance-ledger/123', false)).toBe(true)
    expect(isFinanceHiddenPath('/settlements/abc', false)).toBe(true)
  })
  it('접두사만 겹치는 경로는 오인하지 않는다', () => {
    expect(isFinanceHiddenPath('/observer', false)).toBe(false)
    expect(isFinanceHiddenPath('/buyers-extra', false)).toBe(false)
  })
  it('은닉 대상이 아닌 유지 경로는 false', () => {
    for (const p of ['/dashboard', '/projects', '/asset-vehicles', '/clients', '/guide', '/assets'])
      expect(isFinanceHiddenPath(p, false)).toBe(false)
  })
})

describe('filterFinanceRoutes', () => {
  // 실제 RequireAuth 하위 라우트 경로를 대표하는 픽스처(은닉 6 + 유지 일부)
  const routes = [
    { path: '/' },
    { path: '/dashboard' },
    { path: '/observe' },
    { path: '/buyers' },
    { path: '/portal-accounts' },
    { path: '/finance-ledger' },
    { path: '/asset-report' },
    { path: '/settlements' },
    { path: '/asset-vehicles' },
    { path: '/projects' },
    { path: '/guide' },
    { element: 'noPath' } as { path?: string; element?: string },
  ]

  it('ON이면 원본 배열 참조를 그대로 반환(회귀 0)', () => {
    expect(filterFinanceRoutes(routes, true)).toBe(routes)
  })

  it('OFF(포털도 OFF)면 은닉 전 경로만 제거하고 유지 경로/무path 노드는 보존', () => {
    const out = filterFinanceRoutes(routes, false, false)
    const paths = out.map((r) => r.path)
    for (const hidden of FINANCE_HIDDEN_PATHS) expect(paths).not.toContain(hidden)
    for (const kept of ['/', '/dashboard', '/asset-vehicles', '/projects', '/guide'])
      expect(paths).toContain(kept)
    // path 없는 노드(레이아웃 등)는 유지
    expect(out.some((r) => !r.path)).toBe(true)
  })

  it('재무 OFF + 포털 ON이면 /portal-accounts 라우트만 생존', () => {
    const paths = filterFinanceRoutes(routes, false, true).map((r) => r.path)
    expect(paths).toContain('/portal-accounts')
    for (const hidden of FINANCE_HIDDEN_PATHS.filter((p) => p !== '/portal-accounts'))
      expect(paths).not.toContain(hidden)
  })
})

describe('includePortalRoutes', () => {
  it('PORTAL_FEATURES를 그대로 따른다(테스트 env는 FINANCE on → true)', () => {
    expect(includePortalRoutes()).toBe(PORTAL_FEATURES)
    expect(includePortalRoutes()).toBe(true)
  })
})
