import { describe, expect, it } from 'vitest'
import type { UserRole } from '../types'
import { ROLE_LABELS, roleLabel } from './roles'

describe('ROLE_LABELS', () => {
  it('내부·외부 전 역할 키에 한글 라벨이 존재', () => {
    const roles: UserRole[] = ['ADMIN', 'MANAGER', 'STAFF', 'OBSERVER', 'PARTNER', 'INVESTOR']
    for (const r of roles) {
      expect(ROLE_LABELS[r]).toBeTruthy()
    }
    expect(ROLE_LABELS.ADMIN).toBe('관리자')
    expect(ROLE_LABELS.INVESTOR).toBe('투자·금융사')
  })
})

describe('roleLabel', () => {
  it('알려진 역할 → 한글 라벨', () => {
    expect(roleLabel('MANAGER')).toBe('팀장')
    expect(roleLabel('OBSERVER')).toBe('경영전략실')
  })
  it('미지의 역할 → 원문 그대로', () => {
    expect(roleLabel('SUPERUSER')).toBe('SUPERUSER')
  })
  it('빈값(null/undefined/빈문자) → 빈문자', () => {
    expect(roleLabel(null)).toBe('')
    expect(roleLabel(undefined)).toBe('')
    expect(roleLabel('')).toBe('')
  })
})
