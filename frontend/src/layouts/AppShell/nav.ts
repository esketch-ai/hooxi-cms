// LNB 메뉴 트리 — SCREEN_DESIGN_PLAN §2.1 확정안 그대로
import type { Icon } from '@phosphor-icons/react'
import {
  Bank,
  BookOpenText,
  Buildings,
  Bus,
  ChartBar,
  CalendarDots,
  ChatCircleDots,
  ClockCounterClockwise,
  Eye,
  FolderOpen, // v2에서 ph-folder-notch-open → FolderOpen으로 통합
  Gear,
  IdentificationCard,
  Kanban,
  LockKey,
  Receipt,
  PaperPlaneTilt,
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
  /** 지정 시 해당 role만 노출 (그룹 roles보다 세분화된 항목 단위 제한) */
  roles?: UserRole[]
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
    items: [
      { label: '통합 현황판', path: '/dashboard', icon: SquaresFour },
      // 경영 관찰(읽기 전용) — 전 내부역할 노출. OBSERVER는 화이트리스트라 이 항목이 보임.
      { label: '경영 관찰', path: '/observe', icon: Eye },
    ],
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
      { label: '매수자 마스터', path: '/buyers', icon: Bank, roles: ['ADMIN', 'MANAGER', 'STAFF'] },
      { label: '자산·연동 마스터', path: '/assets', icon: Truck },
      { label: '계정 점검', path: '/accounts', icon: LockKey },
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
      {
        label: '전기버스 자산',
        path: '/asset-vehicles',
        icon: Bus,
        roles: ['ADMIN', 'MANAGER', 'STAFF', 'OBSERVER'],
      },
      {
        label: '재무 원장',
        path: '/finance-ledger',
        icon: Receipt,
        roles: ['ADMIN', 'MANAGER', 'STAFF', 'OBSERVER'],
      },
      {
        label: '자산관리 보고',
        path: '/asset-report',
        icon: ChartBar,
        roles: ['ADMIN', 'MANAGER', 'STAFF', 'OBSERVER'],
      },
    ],
  },
  {
    label: 'SYSTEM',
    items: [
      {
        label: '외부 포털 계정',
        path: '/portal-accounts',
        icon: IdentificationCard,
        roles: ['ADMIN', 'MANAGER'],
      },
      { label: '환경 설정', path: '/settings', icon: Gear, roles: ['ADMIN', 'MANAGER'] },
      { label: '사용자 가이드', path: '/guide', icon: BookOpenText },
    ],
  },
]
