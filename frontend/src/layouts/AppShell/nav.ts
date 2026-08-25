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
  UploadSimple,
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
      { label: '데이터 업로드 센터', path: '/data-import', icon: UploadSimple, roles: ['ADMIN', 'MANAGER', 'STAFF'] },
      { label: '고객사 마스터', path: '/clients', icon: Buildings },
      { label: '매수자 마스터', path: '/buyers', icon: Bank, roles: ['ADMIN', 'MANAGER', 'STAFF'] },
      { label: '자산·연동 마스터', path: '/assets', icon: Truck },
      { label: '계정 점검', path: '/accounts', icon: LockKey },
    ],
  },
  {
    // 감축 도메인 통합 그룹 — 사업(사업중심)·전기버스 자산(차량 크로스)·산정 워크벤치(방법론)
    // 을 한 축으로 모아 차량 생애주기 동선을 드러낸다(도메인 축 재편, URL·권한 불변).
    label: '감축 사업·차량',
    items: [
      { label: '감축 사업 관리', path: '/projects', icon: TreeStructure },
      {
        label: '전기버스 자산',
        path: '/asset-vehicles',
        icon: Bus,
        roles: ['ADMIN', 'MANAGER', 'STAFF', 'OBSERVER'],
      },
      // 구 '감축 참여 레지스트리' — 산정 파이프라인(원장·산정·로그·3단계)임을 명확히.
      // 고객사 '감축 참여' 탭과의 명칭 충돌 해소.
      { label: '감축 산정 워크벤치', path: '/registry', icon: ChartBar, roles: ['ADMIN', 'MANAGER', 'STAFF'] },
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
    label: '재무·정산',
    items: [
      {
        label: '세금계산서 원장',
        path: '/tax-invoices',
        icon: Receipt,
        roles: ['ADMIN', 'MANAGER', 'STAFF'],
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

// ── LNB 허브 — 재무·정산 그룹의 3개 세부 원장을 '재무 관리' 1항목으로 표시 축약.
//    URL·권한 키는 불변(개별 화면 경로가 그대로 살아있고 서브탭 전환, 접근 그룹 매트릭스도 종전 세분).
//    ('자산 관리' 허브는 도메인 재편으로 전기버스 자산이 감축 그룹으로 이동해 폐지 — 항목 직접 표시)
export interface NavHub {
  label: string
  icon: Icon
  /** 이 허브로 묶이는 메뉴 경로들 — 첫 '표시 가능' 경로가 허브의 링크가 된다 */
  paths: string[]
}

export const NAV_HUBS: NavHub[] = [
  { label: '재무 관리', icon: Receipt, paths: ['/finance-ledger', '/settlements', '/tax-invoices'] },
  // 자산·연동 + 계정 점검 — 같은 tb_asset의 두 뷰를 한 메뉴·서브탭으로 통합(개편 P4)
  { label: '자산·연동', icon: Truck, paths: ['/assets', '/accounts'] },
]

/** 필터(재무 OFF·role·observer·그룹허용)를 통과하고 남은 항목에 적용 — 시각 축약만 담당 */
export interface NavItemView extends NavItem {
  /** 허브 항목일 때 — 활성 하이라이트 판정용 소속 경로 목록 */
  matchPaths?: string[]
}

export function collapseHubs(groups: { label: string; items: NavItem[] }[]): {
  label: string
  items: NavItemView[]
}[] {
  return groups.map((group) => {
    const out: NavItemView[] = []
    const consumed = new Set<string>()
    for (const item of group.items) {
      const hub = NAV_HUBS.find((h) => h.paths.includes(item.path))
      if (!hub) {
        out.push(item)
        continue
      }
      if (consumed.has(hub.label)) continue // 이미 허브로 접힘
      consumed.add(hub.label)
      // 생존 항목 중 허브 소속만 — 순서·대표 링크는 허브 정의(paths) 순서를 따른다
      // (예: '재무 관리'는 재무 원장이 대표 — NAV 정의 순서와 무관하게 일관)
      const present = new Set(group.items.map((i) => i.path))
      const survivors = hub.paths.filter((p) => present.has(p))
      out.push({ ...item, label: hub.label, icon: hub.icon, path: survivors[0], matchPaths: survivors })
    }
    return { ...group, items: out }
  })
}

/**
 * 재무 기능 OFF 시 은닉 경로 항목을 제거한 nav 그룹(항목이 모두 사라진 그룹도 제거).
 * financeEnabled=true(ON)면 원본 NAV_GROUPS를 그대로 반환(회귀 0).
 */
export function visibleNavGroups(
  financeEnabled: boolean,
  portalEnabled?: boolean,
): NavGroup[] {
  if (financeEnabled) return NAV_GROUPS
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => !isFinanceHiddenPath(item.path, portalEnabled)),
  })).filter((group) => group.items.length > 0)
}
