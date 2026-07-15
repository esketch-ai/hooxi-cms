import { NavLink } from 'react-router-dom'
import { SignOut, X } from '@phosphor-icons/react'
import { useAuth } from '../../app/AuthProvider'
import { useChatBadge } from '../../lib/api/queries'
import { NAV_GROUPS } from './nav'

interface SidebarProps {
  /** 모바일 오버레이 열림 상태 */
  mobileOpen: boolean
  onMobileClose: () => void
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth()
  const { data: chatBadge } = useChatBadge()
  const waiting = chatBadge?.waiting ?? 0

  const groups = NAV_GROUPS.filter(
    (group) => !group.roles || (user && group.roles.includes(user.role)),
  )

  const initial = user?.name?.charAt(0) ?? '?'

  return (
    <div className="flex h-full flex-col">
      {/* 로고(HOOXI PARTNERS) + CMS 텍스트 — 중앙 정렬, 다크는 로고 흰색화 */}
      <div className="flex h-16 shrink-0 items-center justify-center gap-2 border-b border-hairline px-4">
        <img
          src="/hooxipartners_logo_trans.png"
          alt="Hooxi Partners"
          className="h-7 w-auto dark:brightness-0 dark:invert"
        />
        <span className="text-lg font-semibold tracking-tight text-red-600 dark:text-red-500">
          CMS
        </span>
      </div>

      {/* 메뉴 트리 */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {groups.map((group) => (
          <div key={group.label} className="mb-5">
            <p className="mb-1.5 px-2 text-xs font-semibold tracking-wider text-slatey uppercase">
              {group.label}
            </p>
            <ul className="space-y-0.5">
              {group.items.map((item) => (
                <li key={item.path}>
                  <NavLink
                    to={item.path}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      `flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors pointer-coarse:py-3 ${
                        isActive
                          ? 'bg-elevate-strong font-semibold text-bone'
                          : 'text-ash hover:bg-elevate hover:text-bone'
                      }`
                    }
                  >
                    <item.icon size={18} />
                    <span className="truncate">{item.label}</span>
                    {item.badgeKey === 'chat' && waiting > 0 && (
                      <span
                        className="ml-auto inline-flex min-w-[18px] shrink-0 items-center justify-center rounded-full bg-rose-500 px-1.5 py-0.5 text-[10px] font-bold text-white"
                        title={`직원 연결 대기 ${waiting}건`}
                      >
                        {waiting > 99 ? '99+' : waiting}
                      </span>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      {/* 하단 프로필 + 로그아웃 */}
      <div className="shrink-0 border-t border-hairline p-3">
        <div className="flex items-center gap-2.5 rounded-lg px-2 py-1.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-elevate-strong text-sm font-semibold text-bone">
            {initial}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-bone">
              {user?.name ?? '—'}
            </p>
            <p className="truncate text-xs text-slatey">
              {user?.position || user?.email || ''}
            </p>
          </div>
          <button
            type="button"
            onClick={logout}
            className="rounded-md p-1.5 text-smoke hover:bg-elevate hover:text-bone pointer-coarse:p-3"
            title="로그아웃"
            aria-label="로그아웃"
          >
            <SignOut size={18} />
          </button>
        </div>
      </div>
    </div>
  )
}

export function Sidebar({ mobileOpen, onMobileClose }: SidebarProps) {
  return (
    <>
      {/* 데스크톱 고정 LNB (w-64) */}
      <aside className="hidden w-64 shrink-0 border-r border-hairline bg-graphite lg:block">
        <SidebarContent />
      </aside>

      {/* 모바일 오버레이 슬라이드 */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
          <div
            className="absolute inset-0 bg-black/70"
            onClick={onMobileClose}
            aria-hidden="true"
          />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-hairline bg-graphite">
            <button
              type="button"
              onClick={onMobileClose}
              className="absolute top-4 right-3 z-10 rounded-md p-1.5 text-smoke hover:bg-elevate hover:text-bone"
              aria-label="메뉴 닫기"
            >
              <X size={20} />
            </button>
            <SidebarContent onNavigate={onMobileClose} />
          </aside>
        </div>
      )}
    </>
  )
}
