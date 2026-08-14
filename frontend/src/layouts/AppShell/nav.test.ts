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
