// LNB 메뉴 트리 — SCREEN_DESIGN_PLAN §2.1 확정안 그대로
import type { Icon } from '@phosphor-icons/react'
import {
  Buildings,
  CalendarDots,
  ChatCircleDots,
  ClockCounterClockwise,
  FolderOpen, // v2에서 ph-folder-notch-open → FolderOpen으로 통합
  Gear,
  Kanban,
  LockKey,
  PaperPlaneTilt,
  Receipt,
  SquaresFour,
  TreeStructure,
  Truck,
} from '@phosphor-icons/react'
import type { UserRole } from '../../types'

export interface NavItem {
  label: string
  path: string
  icon: Icon
  /** 지정 시 해당 카운트 뱃지 폴링 표시 (chat: GET /chat/badge waiting) */
  badgeKey?: 'chat'
}

export interface NavGroup {
  label: string
  /** 지정 시 해당 role만 노출 */
  roles?: UserRole[]
  items: NavItem[]
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: 'DASHBOARD',
    items: [{ label: '통합 현황판', path: '/dashboard', icon: SquaresFour }],
  },
  {
    label: 'WORK',
    items: [
      { label: '이슈 보드', path: '/issues', icon: Kanban },
      { label: '일정 캘린더', path: '/calendar', icon: CalendarDots },
    ],
  },
  {
    label: 'MASTER DATA',
    items: [
      { label: '고객사 마스터', path: '/clients', icon: Buildings },
      { label: '자산 및 연동 현황', path: '/assets', icon: Truck },
      { label: '수집 계정 관리', path: '/accounts', icon: LockKey },
    ],
  },
  {
    label: 'CRM / COMM',
    items: [
      { label: '영업 활동 이력', path: '/histories', icon: ClockCounterClockwise },
      { label: '카카오톡 상담 관제', path: '/chat', icon: ChatCircleDots, badgeKey: 'chat' },
    ],
  },
  {
    label: 'REPORT & DOCS',
    items: [
      { label: '월간 보고서 발송 관리', path: '/reports', icon: PaperPlaneTilt },
      { label: '문서 아카이브', path: '/documents', icon: FolderOpen },
    ],
  },
  {
    label: 'PROJECT & FINANCE',
    items: [
      { label: '감축 사업 관리', path: '/projects', icon: TreeStructure },
      { label: '고객사별 정산 현황', path: '/settlements', icon: Receipt },
    ],
  },
  {
    label: 'SYSTEM',
    roles: ['ADMIN', 'MANAGER'],
    items: [{ label: '환경 설정', path: '/settings', icon: Gear }],
  },
]
