import { NavLink } from 'react-router-dom'
import { Leaf, SignOut, X } from '@phosphor-icons/react'
import { useAuth } from '../../app/AuthProvider'
import { NAV_GROUPS } from './nav'

interface SidebarProps {
  /** 모바일 오버레이 열림 상태 */
  mobileOpen: boolean
  onMobileClose: () => void
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth()

  const groups = NAV_GROUPS.filter(
    (group) => !group.roles || (user && group.roles.includes(user.role)),
  )

  const initial = user?.name?.charAt(0) ?? '?'

  return (
    <div className="flex h-full flex-col">
      {/* 로고 */}
      <div className="flex h-16 shrink-0 items-center gap-2 border-b border-slate-100 px-5">
        <Leaf size={22} weight="fill" className="text-emerald-500" />
        <span className="text-base font-bold tracking-tight text-slate-900">
          Carbon Fleet
        </span>
      </div>

      {/* 메뉴 트리 */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {groups.map((group) => (
          <div key={group.label} className="mb-5">
            <p className="mb-1.5 px-2 text-xs font-semibold tracking-wider text-slate-400 uppercase">
              {group.label}
            </p>
            <ul className="space-y-0.5">
              {group.items.map((item) => (
                <li key={item.path}>
                  <NavLink
                    to={item.path}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      `flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                        isActive
                          ? 'bg-slate-100 font-semibold text-slate-900'
                          : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                      }`
                    }
                  >
                    <item.icon size={18} />
                    <span className="truncate">{item.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      {/* 하단 프로필 + 로그아웃 */}
      <div className="shrink-0 border-t border-slate-100 p-3">
        <div className="flex items-center gap-2.5 rounded-lg px-2 py-1.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-800 text-sm font-semibold text-white">
            {initial}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-slate-800">
              {user?.name ?? '—'}
            </p>
            <p className="truncate text-xs text-slate-400">
              {user?.position || user?.email || ''}
            </p>
          </div>
          <button
            type="button"
            onClick={logout}
            className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
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
      <aside className="hidden w-64 shrink-0 border-r border-slate-200 bg-white lg:block">
        <SidebarContent />
      </aside>

      {/* 모바일 오버레이 슬라이드 */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
          <div
            className="absolute inset-0 bg-slate-900/40"
            onClick={onMobileClose}
            aria-hidden="true"
          />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-white shadow-xl">
            <button
              type="button"
              onClick={onMobileClose}
              className="absolute top-4 right-3 z-10 rounded-md p-1.5 text-slate-400 hover:bg-slate-100"
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
