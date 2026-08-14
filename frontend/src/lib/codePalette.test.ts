import { describe, expect, it } from 'vitest'
import {
  CODE_PALETTE,
  PALETTE_ORDER,
  badgeClassOf,
  dotClassOf,
  hexOf,
} from './codePalette'

describe('CODE_PALETTE / PALETTE_ORDER', () => {
  it('각 색상 스펙은 badge·dot·hex·label을 모두 가진다', () => {
    for (const spec of Object.values(CODE_PALETTE)) {
      expect(spec.badge).toBeTruthy()
      expect(spec.dot).toBeTruthy()
      expect(spec.hex).toMatch(/^#[0-9a-f]{6}$/)
      expect(spec.label).toBeTruthy()
    }
  })
  it('PALETTE_ORDER는 정의된 색상만 담고 중복이 없다', () => {
    const keys = Object.keys(CODE_PALETTE)
    expect(PALETTE_ORDER).toHaveLength(keys.length)
    expect(new Set(PALETTE_ORDER).size).toBe(PALETTE_ORDER.length)
    for (const c of PALETTE_ORDER) expect(keys).toContain(c)
  })
})

describe('badgeClassOf', () => {
  it('알려진 색 → 해당 badge 클래스', () => {
    expect(badgeClassOf('emerald')).toBe(CODE_PALETTE.emerald.badge)
  })
  it('미지정/미지원 → 회색 폴백', () => {
    const gray = CODE_PALETTE.gray.badge
    expect(badgeClassOf(null)).toBe(gray)
    expect(badgeClassOf(undefined)).toBe(gray)
    expect(badgeClassOf('nope')).toBe(gray)
  })
})

describe('dotClassOf', () => {
  it('알려진 색 → 해당 dot 클래스', () => {
    expect(dotClassOf('blue')).toBe(CODE_PALETTE.blue.dot)
  })
  it('미지정/미지원 → 회색 dot 폴백', () => {
    expect(dotClassOf(null)).toBe(CODE_PALETTE.gray.dot)
    expect(dotClassOf('nope')).toBe(CODE_PALETTE.gray.dot)
  })
})

describe('hexOf', () => {
  it('알려진 색 → 해당 hex', () => {
    expect(hexOf('rose')).toBe(CODE_PALETTE.rose.hex)
  })
  it('미지정/미지원 → 회색 hex 폴백', () => {
    expect(hexOf(null)).toBe(CODE_PALETTE.gray.hex)
    expect(hexOf('nope')).toBe(CODE_PALETTE.gray.hex)
  })
})
