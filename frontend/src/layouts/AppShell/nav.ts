// LNB 메뉴 트리 — SCREEN_DESIGN_PLAN §2.1 확정안 그대로
import { isFinanceHiddenPath } from '../../lib/featureFlags'
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
  Wallet,
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
        label: '세금계산서 원장',
        path: '/tax-invoices',
        icon: Receipt,
        roles: ['ADMIN', 'MANAGER', 'STAFF'],
      },
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
      {
        // P4 정산 관리 — 내부 전용(OBSERVER 제외). 상태전이는 MANAGER↑, 청구취소는 ADMIN.
        label: '정산 관리',
        path: '/settlements',
        icon: Wallet,
        roles: ['ADMIN', 'MANAGER', 'STAFF'],
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

/** 전체 메뉴 경로(정본) — 그룹 접근 가드(G4)의 판정 대상 목록 */
export const ALL_MENU_PATHS: string[] = NAV_GROUPS.flatMap((g) => g.items.map((i) => i.path))

/**
 * 재무 기능 OFF 시 은닉 경로 항목을 제거한 nav 그룹(항목이 모두 사라진 그룹도 제거).
 * financeEnabled=true(ON)면 원본 NAV_GROUPS를 그대로 반환(회귀 0).
 */
export function visibleNavGroups(financeEnabled: boolean): NavGroup[] {
  if (financeEnabled) return NAV_GROUPS
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => !isFinanceHiddenPath(item.path)),
  })).filter((group) => group.items.length > 0)
}
