import { describe, expect, it } from 'vitest'
import { FINANCE_COLUMN_KEYS, visibleAssetVehicleColumns } from './AssetVehiclesPage'

// AV-3 전기버스 자산 — 재무 OFF 시 금액 컬럼 은닉(감축·제원 컬럼은 유지).
const cols = [
  { key: 'project' },
  { key: 'vehicle_no' },
  { key: 'total_reduction' },
  { key: 'effective_reduction' },
  { key: 'expected_payout' },
  { key: 'expected_revenue' },
  { key: 'project_revenue' },
  { key: 'project_cost' },
]

describe('visibleAssetVehicleColumns', () => {
  it('ON이면 원본 컬럼 그대로(회귀 0)', () => {
    expect(visibleAssetVehicleColumns(cols, true)).toBe(cols)
  })

  it('OFF면 금액 컬럼(예상지급액·예상수익·매출·원가) 제거', () => {
    const keys = visibleAssetVehicleColumns(cols, false).map((c) => c.key)
    for (const k of FINANCE_COLUMN_KEYS) expect(keys).not.toContain(k)
  })

  it('OFF면 예상수익 컬럼이 은닉된다(B3)', () => {
    const keys = visibleAssetVehicleColumns(cols, false).map((c) => c.key)
    expect(keys).not.toContain('expected_revenue')
  })

  it('ON이면 예상수익 컬럼이 유지된다(B3)', () => {
    const keys = visibleAssetVehicleColumns(cols, true).map((c) => c.key)
    expect(keys).toContain('expected_revenue')
  })

  it('OFF여도 차량·감축 컬럼은 유지', () => {
    const keys = visibleAssetVehicleColumns(cols, false).map((c) => c.key)
    for (const k of ['project', 'vehicle_no', 'total_reduction', 'effective_reduction'])
      expect(keys).toContain(k)
  })
})
