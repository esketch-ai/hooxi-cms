// 권한 부족 시 전면 안내 — 종전 SettingsPage 로컬 AdminOnlyNotice를 승격(표현 전용).
import { ShieldCheck } from '@phosphor-icons/react'
import { EmptyState } from './EmptyState'
import { roleLabel } from '../lib/roles'
import type { UserRole } from '../types'

interface PermissionNoticeProps {
  /** 대상 기능명 (예: "공통 코드 관리") */
  feature: string
  /** 조회·변경에 필요한 역할 (기본 ADMIN 단독) */
  requires?: UserRole[]
}

export function PermissionNotice({ feature, requires = ['ADMIN'] }: PermissionNoticeProps) {
  // "관리자(ADMIN)" 형태로 나열 — 종전 문구와 동등하게 라벨(코드) 병기
  const rolesText = requires.map((r) => `${roleLabel(r)}(${r})`).join('·')
  // 제목도 requires에서 파생(재사용 정확성). ADMIN 단독은 종전 문구 그대로 보존.
  const title =
    requires.length === 1 && requires[0] === 'ADMIN'
      ? 'ADMIN 전용 기능입니다'
      : `${rolesText} 전용 기능입니다`
  return (
    <EmptyState
      icon={<ShieldCheck size={36} />}
      title={title}
      description={`${feature}은(는) ${rolesText} 권한으로만 조회·변경할 수 있습니다.`}
    />
  )
}
