// 호환성 게이트 — rolldown 기반 vite 8 × vitest 4 트랜스폼 동작 조기 확인.
import { describe, expect, it } from 'vitest'

describe('sanity', () => {
  it('runs vitest under vite 8', () => {
    expect(1 + 1).toBe(2)
  })
})
