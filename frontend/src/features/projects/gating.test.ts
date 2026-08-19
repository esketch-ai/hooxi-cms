import { describe, expect, it } from 'vitest'
import { visibleProjectTabs } from './ProjectDetailPage'

// SCR-06 사업 상세 — 재무 OFF 시 finance 탭 은닉(개요·차량 탭은 유지).
describe('visibleProjectTabs', () => {
  it('ON이면 finance 탭 포함(회귀 0)', () => {
    const keys = visibleProjectTabs(true).map((t) => t.key)
    expect(keys).toEqual(['overview', 'vehicles', 'finance'])
  })

  it('OFF면 finance 탭 제거, 기본탭 overview는 유지', () => {
    const keys = visibleProjectTabs(false).map((t) => t.key)
    expect(keys).not.toContain('finance')
    expect(keys).toContain('overview')
    expect(keys).toContain('vehicles')
    expect(keys[0]).toBe('overview')
  })
})
