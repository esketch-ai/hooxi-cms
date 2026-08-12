// Phase 4 포털 셸 — 내부 사이드바/네비 없이 상단 헤더 + <Outlet/>만. 내부 AppShell과 완전 분리.
import { Link, Navigate, Outlet } from 'react-router-dom'
import { CircleNotch, Leaf, SignOut } from '@phosphor-icons/react'
import { usePortalAuth } from './PortalAuthProvider'

const ROLE_BADGE: Record<string, string> = {
  PARTNER: '운수사',
  INVESTOR: '투자·금융사',
}

/** 포털 미인증(me 없음) 접근 시 /portal/login 리다이렉트 */
export function RequirePortal() {
  const { me, isLoading } = usePortalAuth()

  if (isLoading) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-void">
        <CircleNotch size={28} className="animate-spin text-slatey" />
      </div>
    )
  }

  if (!me) {
    return <Navigate to="/portal/login" replace />
  }

  return <PortalShell />
}

function PortalShell() {
  const { me, logout } = usePortalAuth()

  return (
    <div className="min-h-dvh bg-void">
      <header className="sticky top-0 z-10 border-b border-hairline bg-graphite/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Link to="/portal" className="flex items-center gap-2.5">
            <span className="hero-horizon inline-flex h-9 w-9 items-center justify-center rounded-xl">
              <Leaf size={18} weight="fill" className="text-white" />
            </span>
            <span className="text-base font-semibold tracking-tight text-bone">
              후시 파트너 포털
            </span>
          </Link>
          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              {me?.org_name && (
                <p className="text-sm font-medium text-bone">{me.org_name}</p>
              )}
              <p className="text-xs text-slatey">
                {me ? ROLE_BADGE[me.role] ?? me.role : ''}
              </p>
            </div>
            <button
              type="button"
              onClick={logout}
              className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-3 py-1.5 text-xs font-medium text-bone hover:bg-elevate"
            >
              <SignOut size={15} />
              로그아웃
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  )
}
