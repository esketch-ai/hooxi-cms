// 그룹 메뉴 접근(G4) — enforce에서만 필터·가드, ADMIN/OBSERVER/off·monitor 불변
import { describe, expect, it } from 'vitest'
import { groupHome, isMenuAllowed, isPathAllowedForUser } from './menuAccess'
import type { User } from '../types'

const base: User = {
  user_id: 'u1', email: 'a@b.c', name: '홍길동', role: 'STAFF', status: 'ACTIVE', pin_set: true,
}

describe('isMenuAllowed', () => {
  it('off/monitor 모드는 항상 허용(회귀 0)', () => {
    expect(isMenuAllowed({ ...base, access_mode: 'off', allowed_menus: ['/clients'] }, '/settlements')).toBe(true)
    expect(isMenuAllowed({ ...base, access_mode: 'monitor', allowed_menus: ['/clients'] }, '/settlements')).toBe(true)
  })
  it('enforce: 허용 목록으로 판정', () => {
    const u: User = { ...base, access_mode: 'enforce', allowed_menus: ['/clients', '/guide'] }
    expect(isMenuAllowed(u, '/clients')).toBe(true)
    expect(isMenuAllowed(u, '/settlements')).toBe(false)
  })
  it('ADMIN·OBSERVER는 enforce여도 우회(OBSERVER는 별도 화이트리스트)', () => {
    expect(isMenuAllowed({ ...base, role: 'ADMIN', access_mode: 'enforce', allowed_menus: [] }, '/settlements')).toBe(true)
    expect(isMenuAllowed({ ...base, role: 'OBSERVER', access_mode: 'enforce', allowed_menus: [] }, '/observe')).toBe(true)
  })
  it('허용 목록이 비어있으면 fail-safe 개방', () => {
    expect(isMenuAllowed({ ...base, access_mode: 'enforce', allowed_menus: [] }, '/settlements')).toBe(true)
  })
})

describe('isPathAllowedForUser', () => {
  const menus = ['/clients', '/settlements', '/reports']
  const u: User = { ...base, access_mode: 'enforce', allowed_menus: ['/clients', '/reports'] }
  it('하위 경로는 base 메뉴로 판정', () => {
    expect(isPathAllowedForUser(u, '/clients/abc', menus)).toBe(true)
    expect(isPathAllowedForUser(u, '/settlements/xyz', menus)).toBe(false)
    expect(isPathAllowedForUser(u, '/reports/segments', menus)).toBe(true)
  })
  it('메뉴 정본에 없는 경로(/map 등)는 게이트 대상 아님', () => {
    expect(isPathAllowedForUser(u, '/map', menus)).toBe(true)
  })
})

describe('groupHome', () => {
  it('enforce + 허용 홈이면 그룹 홈, 비허용이면 허용 경로로 폴백', () => {
    expect(groupHome({ ...base, access_mode: 'enforce', allowed_menus: ['/assets'], home_path: '/assets' })).toBe('/assets')
    // home(/assets) 비허용·/dashboard도 비허용 → 첫 허용 메뉴(/clients). 반환은 항상 허용 경로(루프 방지)
    expect(groupHome({ ...base, access_mode: 'enforce', allowed_menus: ['/clients'], home_path: '/assets' })).toBe('/clients')
    expect(groupHome({ ...base, access_mode: 'enforce', allowed_menus: ['/dashboard', '/clients'], home_path: '/assets' })).toBe('/dashboard')
    expect(groupHome({ ...base, access_mode: 'off', home_path: '/assets' })).toBe('/dashboard')
  })
  it('무한 루프 방지 — /dashboard도 비허용이면 첫 허용 메뉴로', () => {
    const u = { ...base, access_mode: 'enforce' as const, allowed_menus: ['/assets', '/guide'], home_path: '/settlements' }
    expect(groupHome(u)).toBe('/assets') // home도 /dashboard도 비허용 → 첫 허용 메뉴
    expect(isPathAllowedForUser(u, groupHome(u), ['/dashboard', '/assets', '/settlements'])).toBe(true)
  })
})
