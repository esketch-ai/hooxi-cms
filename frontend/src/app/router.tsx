import { createBrowserRouter, Navigate, Outlet, useLocation, type RouteObject } from 'react-router-dom'
import { CircleNotch } from '@phosphor-icons/react'
import { useAuth } from './AuthProvider'
import { AppShell } from '../layouts/AppShell'
import { isObserverAllowed, OBSERVER_HOME } from '../layouts/AppShell/observerAccess'
import { ALL_MENU_PATHS } from '../layouts/AppShell/nav'
import { groupHome, isPathAllowedForUser } from '../lib/menuAccess'
import { FINANCE_FEATURES, filterFinanceRoutes, includePortalRoutes } from '../lib/featureFlags'
import { PortalAuthProvider } from '../features/portal/PortalAuthProvider'
import { RequirePortal } from '../features/portal/PortalShell'
import { PortalLoginPage } from '../features/portal/PortalLoginPage'
import { PortalProjectsPage } from '../features/portal/PortalProjectsPage'
import { PortalProjectDetailPage } from '../features/portal/PortalProjectDetailPage'
import { LoginPage } from '../features/auth/LoginPage'
import { DashboardPage } from '../features/dashboard/DashboardPage'
import { IssuesPage } from '../features/issues/IssuesPage'
import { CalendarPage } from '../features/calendar/CalendarPage'
import { ClientsPage } from '../features/clients/ClientsPage'
import { ClientDetailPage } from '../features/clients/ClientDetailPage'
import { BuyersPage } from '../features/buyers/BuyersPage'
import { PortalAccountsPage } from '../features/portal-admin/PortalAccountsPage'
import { HistoriesPage } from '../features/histories/HistoriesPage'
import { ReportsPage } from '../features/reports/ReportsPage'
import { SegmentsPage } from '../features/segments/SegmentsPage'
import { DocumentsPage } from '../features/documents/DocumentsPage'
import { SettingsPage } from '../features/settings/SettingsPage'
import { GuideLayout } from '../features/guide/GuideLayout'
import { GuideHubPage } from '../features/guide/GuideHubPage'
import { GuideTopicPage } from '../features/guide/GuideTopicPage'
import { AssetsPage } from '../features/assets/AssetsPage'
import { AssetVehiclesPage } from '../features/asset-vehicles/AssetVehiclesPage'
import { AccountsPage } from '../features/accounts/AccountsPage'
import { ProjectsPage } from '../features/projects/ProjectsPage'
import { ProjectDetailPage } from '../features/projects/ProjectDetailPage'
import { FinanceLedgerPage } from '../features/finance-ledger/FinanceLedgerPage'
import { AssetReportPage } from '../features/asset-report/AssetReportPage'
import { TaxInvoicesPage } from '../features/tax-invoices/TaxInvoicesPage'
import { SettlementsPage } from '../features/settlements/SettlementsPage'
import { ChatPage } from '../features/chat/ChatPage'
import { MapPage } from '../features/map/MapPage'
import { ObservePage } from '../features/observe/ObservePage'

/** 미인증(또는 PENDING·PIN 미설정) 접근 시 /login 리다이렉트 */
function RequireAuth() {
  const { isLoading, isAuthenticated, pinSet, user } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-void">
        <CircleNotch size={28} className="animate-spin text-slatey" />
      </div>
    )
  }

  if (!isAuthenticated || !pinSet) {
    return <Navigate to="/login" replace />
  }

  // OBSERVER(경영 관찰) 격리 — 화이트리스트 밖 경로 접근 시 /observe로 리다이렉트.
  // 기존 3역할·외부 역할은 이 분기를 타지 않아 라우팅 불변(회귀 0).
  if (user?.role === 'OBSERVER' && !isObserverAllowed(location.pathname)) {
    return <Navigate to={OBSERVER_HOME} replace />
  }

  // 그룹 메뉴 접근(G4) — enforce 모드에서 허용 메뉴 밖 경로는 그룹 홈으로(off/monitor 불변).
  // 진짜 차단은 백엔드(access_control) — 여기는 UX 리다이렉트다.
  if (!isPathAllowedForUser(user, location.pathname, ALL_MENU_PATHS)) {
    return <Navigate to={groupHome(user)} replace />
  }

  // AppShell 내부의 <Outlet />이 하위 라우트를 렌더링
  return <AppShell />
}

/** 역할별 홈 — OBSERVER는 /observe, enforce면 그룹 home_path, 그 외는 /dashboard */
function RoleHome() {
  const { user } = useAuth()
  if (user?.role === 'OBSERVER') return <Navigate to={OBSERVER_HOME} replace />
  return <Navigate to={groupHome(user)} replace />
}

/** 외부 포털(Phase 4) 서브트리 — 내부 AuthProvider와 분리된 PortalAuthProvider로만 감싼다 */
function PortalRoot() {
  return (
    <PortalAuthProvider>
      <Outlet />
    </PortalAuthProvider>
  )
}

// ── Phase 4 외부 포털(PARTNER/INVESTOR) — 내부 AppShell/RequireAuth 밖 완전 별도 트리 ──
// 재무 OFF 시 이 서브트리는 라우트에서 통째로 제외한다(직접 URL은 catch-all이 처리).
const portalRoute: RouteObject = {
  element: <PortalRoot />,
  children: [
    { path: '/portal/login', element: <PortalLoginPage /> },
    {
      element: <RequirePortal />,
      children: [
        { path: '/portal', element: <PortalProjectsPage /> },
        { path: '/portal/projects/:projectId', element: <PortalProjectDetailPage /> },
      ],
    },
  ],
}

// RequireAuth 하위 내부 화면 — 재무 OFF면 filterFinanceRoutes가 은닉 6경로를 제거한다.
const appRoutes: RouteObject[] = [
  { path: '/', element: <RoleHome /> },
  // ── P1 구현 화면 ──────────────────────────────────────────────
  { path: '/dashboard', element: <DashboardPage /> }, // SCR-01
  { path: '/observe', element: <ObservePage /> }, // OB-4 경영 관찰(OBSERVER 랜딩, 읽기 전용)
  { path: '/issues', element: <IssuesPage /> }, // SCR-02
  { path: '/calendar', element: <CalendarPage /> }, // SCR-11
  { path: '/clients', element: <ClientsPage /> }, // SCR-03
  { path: '/clients/:clientId', element: <ClientDetailPage /> }, // SCR-03D
  { path: '/buyers', element: <BuyersPage /> }, // INC-8a 매수자 마스터
  { path: '/portal-accounts', element: <PortalAccountsPage /> }, // INC-8b 외부 포털 계정
  { path: '/histories', element: <HistoriesPage /> }, // SCR-05
  { path: '/reports', element: <ReportsPage /> }, // SCR-12
  { path: '/reports/segments', element: <SegmentsPage /> }, // SCR-12 확장 — 세그먼트 발송
  { path: '/documents', element: <DocumentsPage /> }, // SCR-13
  { path: '/settings', element: <SettingsPage /> }, // SCR-14 (계정 관리 탭)
  // 사용자 가이드 (전 역할) — 허브 + 토픽 서브페이지
  {
    path: '/guide',
    element: <GuideLayout />,
    children: [
      { index: true, element: <GuideHubPage /> },
      { path: ':topicId', element: <GuideTopicPage /> },
    ],
  },
  // ── P2 구현 화면 ──────────────────────────────────────────────
  { path: '/assets', element: <AssetsPage /> }, // SCR-04
  { path: '/asset-vehicles', element: <AssetVehiclesPage /> }, // AV-3 전기버스 자산
  { path: '/accounts', element: <AccountsPage /> }, // 수집 계정 관리
  { path: '/projects', element: <ProjectsPage /> }, // SCR-06
  { path: '/projects/:projectId', element: <ProjectDetailPage /> }, // SCR-06 상세
  { path: '/tax-invoices', element: <TaxInvoicesPage /> }, // 세금계산서 원장(홈택스 HTML 자동반영)
  { path: '/finance-ledger', element: <FinanceLedgerPage /> }, // FL-3 재무 원장(사업 grain)
  { path: '/asset-report', element: <AssetReportPage /> }, // P2 자산관리 보고(고객사 grain)
  { path: '/settlements', element: <SettlementsPage /> }, // P4 정산 관리(SCR-07) — 내부 전용, OBSERVER 접근 불가
  // ── P3 구현 화면 ──────────────────────────────────────────────
  { path: '/chat', element: <ChatPage /> }, // SCR-08
  { path: '/map', element: <MapPage /> }, // SCR-09
]

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  // 재무 OFF면 포털 서브트리 제외
  ...(includePortalRoutes(FINANCE_FEATURES) ? [portalRoute] : []),
  {
    element: <RequireAuth />,
    children: filterFinanceRoutes(appRoutes, FINANCE_FEATURES),
  },
  { path: '*', element: <RoleHome /> },
])
