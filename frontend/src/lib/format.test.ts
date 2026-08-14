import { describe, expect, it } from 'vitest'
import {
  dday,
  elapsed,
  elapsedServer,
  fmtDate,
  fmtDateTime,
  fmtDayLabel,
  fmtMoney,
  fmtMonth,
  fmtRate,
  fmtServerDate,
  fmtServerDateTime,
  fmtServerTime,
  fmtTime,
  nowKstTime,
  parseServerUtc,
  telHref,
  toDatetimeLocal,
  todayKst,
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

describe('fmtDateTime / fmtTime', () => {
  // Date 인스턴스는 로컬 시각 그대로 포맷(타임존 파싱 없음)
  const d = new Date(2026, 6, 5, 9, 3) // 로컬 2026-07-05 09:03
  it('Date → "MM-DD HH:mm" / "HH:mm"', () => {
    expect(fmtDateTime(d)).toBe('07-05 09:03')
    expect(fmtTime(d)).toBe('09:03')
  })
  it('빈값 처리 — fmtDateTime은 —, fmtTime은 빈문자', () => {
    expect(fmtDateTime(null)).toBe('—')
    expect(fmtTime(null)).toBe('')
  })
  it('잘못된 값 — fmtDateTime은 원문, fmtTime은 빈문자', () => {
    expect(fmtDateTime('nope')).toBe('nope')
    expect(fmtTime('nope')).toBe('')
  })
})

describe('fmtServerDate / fmtServerDateTime / fmtServerTime', () => {
  // Date 인스턴스를 넘기면 로컬 시각 그대로 포맷(서버 UTC 파싱 우회) → 타임존 무관 결정성
  const d = new Date(2026, 6, 5, 9, 3)
  it('Date → 로컬 포맷', () => {
    expect(fmtServerDate(d)).toBe('2026-07-05')
    expect(fmtServerDateTime(d)).toBe('07-05 09:03')
    expect(fmtServerTime(d)).toBe('09:03')
  })
  it('빈값 처리 — 날짜류는 —, 시각은 빈문자', () => {
    expect(fmtServerDate(null)).toBe('—')
    expect(fmtServerDate('')).toBe('—')
    expect(fmtServerDateTime(undefined)).toBe('—')
    expect(fmtServerTime(null)).toBe('')
  })
  it('잘못된 값 — 날짜류는 원문, 시각은 빈문자', () => {
    expect(fmtServerDate('nope')).toBe('nope')
    expect(fmtServerDateTime('nope')).toBe('nope')
    expect(fmtServerTime('nope')).toBe('')
  })
})

describe('toDatetimeLocal', () => {
  it('Date → "YYYY-MM-DDTHH:mm"', () => {
    expect(toDatetimeLocal(new Date(2026, 6, 5, 9, 3))).toBe('2026-07-05T09:03')
  })
})

describe('elapsed / elapsedServer', () => {
  const isoAgo = (ms: number) => new Date(Date.now() - ms).toISOString()
  it('경과 구간별 라벨 (elapsed)', () => {
    expect(elapsed(isoAgo(10_000))).toBe('방금 전')
    expect(elapsed(isoAgo(5 * 60_000))).toBe('5분 경과')
    expect(elapsed(isoAgo(3 * 3_600_000))).toBe('3시간 경과')
    expect(elapsed(isoAgo(2 * 86_400_000))).toBe('2일 경과')
  })
  it('빈값/잘못된 값 → 빈문자 (elapsed)', () => {
    expect(elapsed(null)).toBe('')
    expect(elapsed('nope')).toBe('')
  })
  it('서버(naive UTC) 버전도 동일 구간 라벨 (elapsedServer)', () => {
    // toISOString의 Z를 떼어 naive UTC로 만들면 parseServerUtc가 UTC로 재해석
    const naiveAgo = (ms: number) => new Date(Date.now() - ms).toISOString().replace('Z', '')
    expect(elapsedServer(naiveAgo(10_000))).toBe('방금 전')
    expect(elapsedServer(naiveAgo(5 * 60_000))).toBe('5분 경과')
    expect(elapsedServer(naiveAgo(3 * 3_600_000))).toBe('3시간 경과')
    expect(elapsedServer(naiveAgo(2 * 86_400_000))).toBe('2일 경과')
    expect(elapsedServer(null)).toBe('')
    expect(elapsedServer('nope')).toBe('')
  })
})

describe('fmtDayLabel', () => {
  it('오늘(KST) → "오늘 · …" 접두', () => {
    expect(fmtDayLabel(todayKst())).toMatch(/^오늘 · /)
  })
  it('그 외 날짜 → "M월 D일 (요일)" 기본형', () => {
    // 2000-01-01(토) — 오늘/어제와 무관한 고정 과거일
    expect(fmtDayLabel('2000-01-01')).toBe('1월 1일 (토)')
  })
  it('잘못된 값 → 원문 그대로', () => {
    expect(fmtDayLabel('nope')).toBe('nope')
  })
})

describe('todayKst / nowKstTime', () => {
  it('todayKst → "YYYY-MM-DD" 형식', () => {
    expect(todayKst()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
  it('nowKstTime → "HHmm" 4자리', () => {
    expect(nowKstTime()).toMatch(/^\d{4}$/)
  })
})
