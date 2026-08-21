// Phase 4 포털 셸 — 내부 사이드바/네비 없이 상단 헤더 + <Outlet/>만. 내부 AppShell과 완전 분리.
// P1: PARTNER(운수사)에게만 계약대수·보고서·정산 탭 노출(INVESTOR는 사업 조회만 — 종전 그대로).
import { Link, Navigate, NavLink, Outlet } from 'react-router-dom'
import { Bus, CircleNotch, FileText, Leaf, SignOut, TreeStructure, Wallet } from '@phosphor-icons/react'
import { usePortalAuth } from './PortalAuthProvider'
import { useLoginConfig } from '../../lib/api/queries'

const ROLE_BADGE: Record<string, string> = {
  PARTNER: '운수사',
  INVESTOR: '투자·금융사',
}

// PARTNER 전용 탭 — 백엔드도 PARTNER 게이트라 INVESTOR에겐 렌더하지 않는다
const PARTNER_TABS = [
  { label: '참여 사업', path: '/portal', icon: TreeStructure, end: true },
  { label: '계약대수 현황', path: '/portal/fleet', icon: Bus },
  { label: '월간 보고서', path: '/portal/reports', icon: FileText },
  { label: '정산 내역', path: '/portal/settlements', icon: Wallet },
]

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
  const { data: loginConfig } = useLoginConfig()
  const kakaoUrl = loginConfig?.kakao_channel_url ?? null

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
            {/* 카카오 문의(K2) — 문의는 카카오 채널 채팅으로(상담 관제 연동) */}
            {kakaoUrl && (
              <a
                href={kakaoUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-full bg-[#FEE500] px-3 py-1.5 text-xs font-bold text-[#191919] hover:brightness-95"
                title="카카오톡 채널에서 문의하기"
              >
                💬 카카오톡 문의
              </a>
            )}
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
        {/* PARTNER 탭 — 운수사 전용 메뉴(INVESTOR는 기존처럼 사업 조회만) */}
        {me?.role === 'PARTNER' && (
          <nav className="mx-auto flex max-w-5xl gap-1 overflow-x-auto px-4 sm:px-6">
            {PARTNER_TABS.map((t) => (
              <NavLink
                key={t.path}
                to={t.path}
                end={t.end}
                className={({ isActive }) =>
                  `flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? 'border-snow text-bone'
                      : 'border-transparent text-slatey hover:text-ash'
                  }`
                }
              >
                <t.icon size={15} />
                {t.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  )
}
