import { describe, expect, it } from 'vitest'
import { OBSERVER_HOME, OBSERVER_PATHS, isObserverAllowed } from './observerAccess'

describe('OBSERVER 상수', () => {
  it('기본 랜딩은 화이트리스트에 포함된 경로', () => {
    expect(OBSERVER_HOME).toBe('/observe')
    expect(OBSERVER_PATHS).toContain(OBSERVER_HOME)
  })
})

describe('isObserverAllowed', () => {
  it('화이트리스트 정확 매칭 → true', () => {
    for (const p of OBSERVER_PATHS) expect(isObserverAllowed(p)).toBe(true)
  })
  it('자산관리 보고(P2)는 OBSERVER 허용 경로', () => {
    expect(OBSERVER_PATHS).toContain('/asset-report')
    expect(isObserverAllowed('/asset-report')).toBe(true)
  })
  it('화이트리스트 하위 경로(startsWith) → true', () => {
    expect(isObserverAllowed('/finance-ledger/123')).toBe(true)
    expect(isObserverAllowed('/guide/reports')).toBe(true)
  })
  it('화이트리스트 밖 경로 → false', () => {
    expect(isObserverAllowed('/dashboard')).toBe(false)
    expect(isObserverAllowed('/clients')).toBe(false)
    expect(isObserverAllowed('/')).toBe(false)
  })
  it('접두사만 겹치는 다른 경로는 하위로 오인하지 않는다', () => {
    // '/observe'로 시작하지만 경계('/')가 없는 경로는 매칭 안 됨
    expect(isObserverAllowed('/observer')).toBe(false)
    expect(isObserverAllowed('/guide-extra')).toBe(false)
  })
})
