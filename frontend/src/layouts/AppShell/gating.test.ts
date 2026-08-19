import { describe, expect, it } from 'vitest'
import { FINANCE_HIDDEN_PATHS } from '../../lib/featureFlags'
import { NAV_GROUPS, visibleNavGroups } from './nav'
import { isObserverAllowed, observerHome, observerPaths } from './observerAccess'

// 재무 OFF 게이팅 — nav 필터/OBSERVER 정합을 flag 인자로 결정적 검증.
describe('visibleNavGroups', () => {
  it('ON이면 NAV_GROUPS 원본을 그대로 반환(회귀 0)', () => {
    expect(visibleNavGroups(true)).toBe(NAV_GROUPS)
  })

  it('OFF면 은닉 6경로 항목이 nav에서 사라진다', () => {
    const paths = visibleNavGroups(false).flatMap((g) => g.items.map((i) => i.path))
    for (const hidden of FINANCE_HIDDEN_PATHS) expect(paths).not.toContain(hidden)
  })

  it('OFF여도 유지 항목은 남는다(대시보드·감축사업·전기버스·가이드·설정)', () => {
    const paths = visibleNavGroups(false).flatMap((g) => g.items.map((i) => i.path))
    for (const kept of ['/dashboard', '/projects', '/asset-vehicles', '/guide', '/settings'])
      expect(paths).toContain(kept)
  })

  it('OFF면 항목이 모두 사라진 그룹은 제거된다', () => {
    for (const g of visibleNavGroups(false)) expect(g.items.length).toBeGreaterThan(0)
  })
})

describe('OBSERVER 화이트리스트/홈 — 재무 OFF 루프 방지', () => {
  it('OFF 홈은 유효 경로 /dashboard이며 화이트리스트에 포함(무한루프 없음)', () => {
    const home = observerHome(false)
    expect(home).toBe('/dashboard')
    expect(observerPaths(false)).toContain(home)
    expect(isObserverAllowed(home, false)).toBe(true)
  })

  it('OFF 화이트리스트는 은닉 경로(/observe·/finance-ledger·/asset-report)를 배제', () => {
    for (const hidden of ['/observe', '/finance-ledger', '/asset-report'])
      expect(isObserverAllowed(hidden, false)).toBe(false)
  })

  it('ON 홈은 기존대로 /observe (회귀 0)', () => {
    expect(observerHome(true)).toBe('/observe')
    expect(isObserverAllowed('/observe', true)).toBe(true)
    expect(isObserverAllowed('/finance-ledger', true)).toBe(true)
  })
})
