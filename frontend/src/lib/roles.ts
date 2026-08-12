// 역할 라벨 공용 유틸 — 내부 역할(ADMIN/MANAGER/STAFF) + 외부 포털 역할(PARTNER/INVESTOR)
// 표현 전용: 인가 판정과 무관하며, 각 화면의 라벨 중복 정의를 이곳으로 수렴한다.
import type { UserRole } from '../types'

export const ROLE_LABELS: Record<UserRole, string> = {
  ADMIN: '관리자',
  MANAGER: '팀장',
  STAFF: '실무',
  OBSERVER: '경영전략실',
  // 외부 포털 역할(Phase 4) — 내부 역할 드롭다운에는 노출하지 않고 라벨 해석용으로만 유지
  PARTNER: '운수사',
  INVESTOR: '투자·금융사',
}

/** 역할 코드를 한글 라벨로. 매핑이 없으면 원문을 그대로 반환한다. */
export function roleLabel(role?: UserRole | string | null): string {
  if (!role) return ''
  return ROLE_LABELS[role as UserRole] ?? role
}
