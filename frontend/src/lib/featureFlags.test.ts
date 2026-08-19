import { describe, expect, it } from 'vitest'
import {
  FINANCE_HIDDEN_PATHS,
  filterFinanceRoutes,
  includePortalRoutes,
  isFinanceHiddenPath,
} from './featureFlags'

// 재무 은닉 게이팅 순수 로직 — flag를 인자로 받아 결정적으로 검증(빌드 env 무관).
describe('isFinanceHiddenPath', () => {
  it('은닉 6경로는 정확 매칭 시 true', () => {
    for (const p of FINANCE_HIDDEN_PATHS) expect(isFinanceHiddenPath(p)).toBe(true)
  })
  it('은닉 경로의 하위 경로(startsWith 경계)도 true', () => {
    expect(isFinanceHiddenPath('/finance-ledger/123')).toBe(true)
    expect(isFinanceHiddenPath('/settlements/abc')).toBe(true)
  })
  it('접두사만 겹치는 경로는 오인하지 않는다', () => {
    expect(isFinanceHiddenPath('/observer')).toBe(false)
    expect(isFinanceHiddenPath('/buyers-extra')).toBe(false)
  })
  it('은닉 대상이 아닌 유지 경로는 false', () => {
    for (const p of ['/dashboard', '/projects', '/asset-vehicles', '/clients', '/guide', '/assets'])
      expect(isFinanceHiddenPath(p)).toBe(false)
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

  it('OFF면 은닉 6경로만 제거하고 유지 경로/무path 노드는 보존', () => {
    const out = filterFinanceRoutes(routes, false)
    const paths = out.map((r) => r.path)
    for (const hidden of FINANCE_HIDDEN_PATHS) expect(paths).not.toContain(hidden)
    for (const kept of ['/', '/dashboard', '/asset-vehicles', '/projects', '/guide'])
      expect(paths).toContain(kept)
    // path 없는 노드(레이아웃 등)는 유지
    expect(out.some((r) => !r.path)).toBe(true)
  })
})

describe('includePortalRoutes', () => {
  it('ON이면 포털 서브트리 포함, OFF면 제외', () => {
    expect(includePortalRoutes(true)).toBe(true)
    expect(includePortalRoutes(false)).toBe(false)
  })
})
