import { describe, expect, it } from 'vitest'
import { clientLabel, makeClientLabel } from './clientLabel'

describe('clientLabel', () => {
  it('지역 · 고객사명 · 구분 순서로 조합', () => {
    expect(
      clientLabel({ company_name: '경성여객', region: '서울', client_type: 'TRANSPORT' }, '운수사'),
    ).toBe('서울 · 경성여객 · 운수사')
  })

  it('지역·구분이 비면 해당 조각 생략', () => {
    expect(clientLabel({ company_name: '경성여객' }, '')).toBe('경성여객')
    expect(clientLabel({ company_name: '경성여객', region: '서울' }, '')).toBe('서울 · 경성여객')
    expect(clientLabel({ company_name: '경성여객', client_type: 'TRANSPORT' }, '운수사')).toBe(
      '경성여객 · 운수사',
    )
  })

  it('typeLabel 미제공 시 코드값으로 폴백', () => {
    expect(clientLabel({ company_name: 'A', region: '경기', client_type: 'BUILDING' })).toBe(
      '경기 · A · BUILDING',
    )
  })

  it('null 안전', () => {
    expect(clientLabel(null)).toBe('')
    expect(clientLabel(undefined)).toBe('')
  })

  it('makeClientLabel — labelOf 해석기 커링', () => {
    const labelOf = (code?: string | null) => (code === 'TRANSPORT' ? '운수사' : (code ?? ''))
    const fn = makeClientLabel(labelOf)
    expect(fn({ company_name: '한빛', region: '부산', client_type: 'TRANSPORT' })).toBe(
      '부산 · 한빛 · 운수사',
    )
  })
})
