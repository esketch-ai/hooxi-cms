import { createBrowserRouter, Navigate } from 'react-router-dom'
import { CircleNotch } from '@phosphor-icons/react'
import { useAuth } from './AuthProvider'
import { AppShell } from '../layouts/AppShell'
import { LoginPage } from '../features/auth/LoginPage'
import { DashboardPage } from '../features/dashboard/DashboardPage'
import { IssuesPage } from '../features/issues/IssuesPage'
import { CalendarPage } from '../features/calendar/CalendarPage'
import { ClientsPage } from '../features/clients/ClientsPage'
import { ClientDetailPage } from '../features/clients/ClientDetailPage'
import { HistoriesPage } from '../features/histories/HistoriesPage'
import { ReportsPage } from '../features/reports/ReportsPage'
import { DocumentsPage } from '../features/documents/DocumentsPage'
import { SettingsPage } from '../features/settings/SettingsPage'
import { AssetsPage } from '../features/assets/AssetsPage'
import { ProjectsPage } from '../features/projects/ProjectsPage'
import { ProjectDetailPage } from '../features/projects/ProjectDetailPage'
import { SettlementsPage } from '../features/settlements/SettlementsPage'
import { ChatPage } from '../features/chat/ChatPage'
import { MapPage } from '../features/map/MapPage'

/** 미인증(또는 PENDING·PIN 미설정) 접근 시 /login 리다이렉트 */
function RequireAuth() {
  const { isLoading, isAuthenticated, pinSet } = useAuth()

  if (isLoading) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-slate-50">
        <CircleNotch size={28} className="animate-spin text-slate-400" />
      </div>
    )
  }

  if (!isAuthenticated || !pinSet) {
    return <Navigate to="/login" replace />
  }

  // AppShell 내부의 <Outlet />이 하위 라우트를 렌더링
  return <AppShell />
}

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
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
      { path: '/histories', element: <HistoriesPage /> }, // SCR-05
      { path: '/reports', element: <ReportsPage /> }, // SCR-12
      { path: '/documents', element: <DocumentsPage /> }, // SCR-13
      { path: '/settings', element: <SettingsPage /> }, // SCR-14 (계정 관리 탭)
      // ── P2 구현 화면 ──────────────────────────────────────────────
      { path: '/assets', element: <AssetsPage /> }, // SCR-04
      { path: '/projects', element: <ProjectsPage /> }, // SCR-06
      { path: '/projects/:projectId', element: <ProjectDetailPage /> }, // SCR-06 상세
      { path: '/settlements', element: <SettlementsPage /> }, // SCR-07
      // ── P3 구현 화면 ──────────────────────────────────────────────
      { path: '/chat', element: <ChatPage /> }, // SCR-08
      { path: '/map', element: <MapPage /> }, // SCR-09
    ],
  },
  { path: '*', element: <Navigate to="/dashboard" replace /> },
])
