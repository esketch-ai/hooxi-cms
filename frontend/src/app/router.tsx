import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom'
import { CircleNotch } from '@phosphor-icons/react'
import { useAuth } from './AuthProvider'
import { AppShell } from '../layouts/AppShell'
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
import { GuidePage } from '../features/guide/GuidePage'
import { AssetsPage } from '../features/assets/AssetsPage'
import { AssetVehiclesPage } from '../features/asset-vehicles/AssetVehiclesPage'
import { AccountsPage } from '../features/accounts/AccountsPage'
import { ProjectsPage } from '../features/projects/ProjectsPage'
import { ProjectDetailPage } from '../features/projects/ProjectDetailPage'
import { ChatPage } from '../features/chat/ChatPage'
import { MapPage } from '../features/map/MapPage'

/** 미인증(또는 PENDING·PIN 미설정) 접근 시 /login 리다이렉트 */
function RequireAuth() {
  const { isLoading, isAuthenticated, pinSet } = useAuth()

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

  // AppShell 내부의 <Outlet />이 하위 라우트를 렌더링
  return <AppShell />
}

/** 외부 포털(Phase 4) 서브트리 — 내부 AuthProvider와 분리된 PortalAuthProvider로만 감싼다 */
function PortalRoot() {
  return (
    <PortalAuthProvider>
      <Outlet />
    </PortalAuthProvider>
  )
}

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  // ── Phase 4 외부 포털(PARTNER/INVESTOR) — 내부 AppShell/RequireAuth 밖 완전 별도 트리 ──
  {
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
  },
  {
    element: <RequireAuth />,
    children: [
      { path: '/', element: <Navigate to="/dashboard" replace /> },
      // ── P1 구현 화면 ──────────────────────────────────────────────
      { path: '/dashboard', element: <DashboardPage /> }, // SCR-01
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
      { path: '/guide', element: <GuidePage /> }, // 사용자 가이드 (전 역할)
      // ── P2 구현 화면 ──────────────────────────────────────────────
      { path: '/assets', element: <AssetsPage /> }, // SCR-04
      { path: '/asset-vehicles', element: <AssetVehiclesPage /> }, // AV-3 전기버스 자산
      { path: '/accounts', element: <AccountsPage /> }, // 수집 계정 관리
      { path: '/projects', element: <ProjectsPage /> }, // SCR-06
      { path: '/projects/:projectId', element: <ProjectDetailPage /> }, // SCR-06 상세
      // ── P3 구현 화면 ──────────────────────────────────────────────
      { path: '/chat', element: <ChatPage /> }, // SCR-08
      { path: '/map', element: <MapPage /> }, // SCR-09
    ],
  },
  { path: '*', element: <Navigate to="/dashboard" replace /> },
])
