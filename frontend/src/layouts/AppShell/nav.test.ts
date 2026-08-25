import { describe, expect, it } from 'vitest'
import type { UserRole } from '../../types'
import { NAV_GROUPS } from './nav'

const VALID_ROLES: UserRole[] = ['ADMIN', 'MANAGER', 'STAFF', 'OBSERVER', 'PARTNER', 'INVESTOR']

const allItems = NAV_GROUPS.flatMap((g) => g.items)

describe('NAV_GROUPS 구조 정합', () => {
  it('그룹 라벨은 비어있지 않고, 각 그룹은 항목을 1개 이상 가진다', () => {
    for (const g of NAV_GROUPS) {
      expect(g.label.trim()).not.toBe('')
      expect(g.items.length).toBeGreaterThan(0)
    }
  })

  it('모든 item.path는 유일하다', () => {
    const paths = allItems.map((i) => i.path)
    expect(new Set(paths).size).toBe(paths.length)
  })

  it('모든 item.path는 "/"로 시작하고 라벨은 비어있지 않다', () => {
    for (const i of allItems) {
      expect(i.path.startsWith('/')).toBe(true)
      expect(i.label.trim()).not.toBe('')
    }
  })

  it('item.roles/group.roles 지정 시 유효한 UserRole만 담는다', () => {
    for (const g of NAV_GROUPS) {
      if (g.roles) for (const r of g.roles) expect(VALID_ROLES).toContain(r)
      for (const i of g.items) {
        if (i.roles) {
          expect(i.roles.length).toBeGreaterThan(0)
          for (const r of i.roles) expect(VALID_ROLES).toContain(r)
        }
      }
    }
  })

  it('badgeKey는 지정 시 알려진 값만 사용한다', () => {
    for (const i of allItems) {
      if (i.badgeKey) expect(i.badgeKey).toBe('chat')
    }
  })
})

describe('collapseHubs (A안 허브 축약)', () => {
  it('재무·정산 4항목 → 2항목(재무 관리 허브 + 자산관리 보고)', async () => {
    const { collapseHubs, NAV_GROUPS } = await import('./nav')
    const collapsed = collapseHubs(NAV_GROUPS)
    const pf = collapsed.find((g) => g.label === '재무·정산')!
    expect(pf.items).toHaveLength(2)
    const labels = pf.items.map((i) => i.label)
    expect(labels).toContain('재무 관리')
    expect(labels).toContain('자산관리 보고')
    // 허브 링크는 첫 소속 경로, matchPaths에 전 소속 경로
    const fin = pf.items.find((i) => i.label === '재무 관리')!
    expect(new Set(fin.matchPaths)).toEqual(new Set(['/finance-ledger', '/settlements', '/tax-invoices']))
    expect(fin.path).toBe('/finance-ledger') // NAV 정의 순서상 첫 소속 경로
  })

  it('감축 사업·차량 그룹 — 사업·전기버스·산정 워크벤치 3항목(허브 없음)', async () => {
    const { collapseHubs, NAV_GROUPS } = await import('./nav')
    const g = collapseHubs(NAV_GROUPS).find((x) => x.label === '감축 사업·차량')!
    const paths = g.items.map((i) => i.path)
    expect(paths).toEqual(['/projects', '/asset-vehicles', '/registry'])
  })

  it('일부 항목이 필터로 빠져도 남은 것만으로 허브 구성(링크=첫 생존 경로)', async () => {
    const { collapseHubs, NAV_GROUPS } = await import('./nav')
    const pf = NAV_GROUPS.find((g) => g.label === '재무·정산')!
    // 재무 원장·세금계산서가 필터로 빠진 상황(예: 그룹 미허용) — 정산만 생존
    const filtered = [{ ...pf, items: pf.items.filter((i) => !['/finance-ledger', '/tax-invoices'].includes(i.path)) }]
    const out = collapseHubs(filtered)[0]
    const fin = out.items.find((i) => i.label === '재무 관리')!
    expect(fin.path).toBe('/settlements')
    expect(fin.matchPaths).toEqual(['/settlements'])
  })

  it('허브 무관 그룹은 불변', async () => {
    const { collapseHubs, NAV_GROUPS } = await import('./nav')
    const master = NAV_GROUPS.find((g) => g.label === 'MASTER DATA')!
    const out = collapseHubs([master])[0]
    expect(out.items.map((i) => i.path)).toEqual(master.items.map((i) => i.path))
  })
})
