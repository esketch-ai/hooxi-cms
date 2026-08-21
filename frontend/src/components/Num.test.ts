// 숫자 표기 규격 — fmt2(소수 최대 2자리·그룹핑) 헬퍼
import { describe, expect, it } from 'vitest'
import { fmt2 } from './Num'

describe('fmt2', () => {
  it('소수 최대 2자리 반올림 + 콤마 그룹핑', () => {
    expect(fmt2(12345.6789)).toBe('12,345.68')
    expect(fmt2(1234567)).toBe('1,234,567')
    expect(fmt2(0.005)).toBe('0.01')
  })
  it('null/빈값은 대시, 비숫자는 원문', () => {
    expect(fmt2(null)).toBe('—')
    expect(fmt2(undefined)).toBe('—')
    expect(fmt2('')).toBe('—')
    expect(fmt2('abc')).toBe('abc')
  })
})
