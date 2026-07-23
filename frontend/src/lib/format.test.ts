import { describe, expect, it } from 'vitest'
import {
  dday,
  fmtDate,
  fmtMoney,
  fmtMonth,
  fmtRate,
  parseServerUtc,
  telHref,
} from './format'

describe('fmtMoney', () => {
  it('null/undefined/빈문자 → 미정', () => {
    expect(fmtMoney(null)).toBe('미정')
    expect(fmtMoney(undefined)).toBe('미정')
    expect(fmtMoney('')).toBe('미정')
  })
  it('숫자·숫자문자열 → 천단위 원 표기', () => {
    expect(fmtMoney(12345678)).toBe('₩ 12,345,678')
    expect(fmtMoney('5000')).toBe('₩ 5,000')
  })
  it('숫자가 아니면 원문 유지', () => {
    expect(fmtMoney('abc')).toBe('abc')
  })
})

describe('fmtRate', () => {
  it('빈값 → —, 값 → "N %"', () => {
    expect(fmtRate(null)).toBe('—')
    expect(fmtRate(12.5)).toBe('12.5 %')
  })
})

describe('fmtDate / fmtMonth', () => {
  it('Date → 로컬 YYYY-MM-DD / YYYY-MM', () => {
    const d = new Date(2026, 6, 5) // 로컬 2026-07-05
    expect(fmtDate(d)).toBe('2026-07-05')
    expect(fmtMonth(d)).toBe('2026-07')
  })
  it('빈값 → —, 잘못된 값 → 원문', () => {
    expect(fmtDate(null)).toBe('—')
    expect(fmtDate('nope')).toBe('nope')
  })
})

describe('parseServerUtc', () => {
  it('타임존 없으면 UTC(Z)로 간주', () => {
    expect(parseServerUtc('2026-07-22T00:00:00').getTime()).toBe(
      Date.parse('2026-07-22T00:00:00Z'),
    )
  })
  it('이미 Z/오프셋이 있으면 그대로', () => {
    expect(parseServerUtc('2026-07-22T00:00:00Z').getTime()).toBe(
      Date.parse('2026-07-22T00:00:00Z'),
    )
  })
})

describe('telHref', () => {
  it('숫자·+ 외 제거', () => {
    expect(telHref('010-1234-5678')).toBe('tel:01012345678')
    expect(telHref(null)).toBe('tel:')
  })
})

describe('dday', () => {
  // 로컬 정오 기준으로 오프셋 → 타임존 경계 flip 회피
  const dueAfter = (days: number) => {
    const d = new Date()
    d.setDate(d.getDate() + days)
    return `${fmtDate(d)}T12:00:00`
  }
  it('오늘 → D-DAY', () => {
    expect(dday(dueAfter(0))?.label).toBe('D-DAY')
  })
  it('미래 → D-N, 3일 이내면 imminent', () => {
    expect(dday(dueAfter(3))).toMatchObject({ label: 'D-3', overdue: false, imminent: true })
    expect(dday(dueAfter(10))).toMatchObject({ label: 'D-10', imminent: false })
  })
  it('과거 → D+N, overdue', () => {
    expect(dday(dueAfter(-2))).toMatchObject({ label: 'D+2', overdue: true })
  })
  it('빈값/잘못된 값 → null', () => {
    expect(dday(null)).toBeNull()
    expect(dday('nope')).toBeNull()
  })
})
