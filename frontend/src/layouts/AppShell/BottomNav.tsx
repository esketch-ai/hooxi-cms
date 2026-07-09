// 모바일 하단 탭 바 4탭: 현황판·고객사·이슈·일정 (플랜 §7 / 01_COMMON §6)
import { NavLink } from 'react-router-dom'
import {
  Buildings,
  CalendarDots,
  Kanban,
  SquaresFour,
} from '@phosphor-icons/react'

const TABS = [
  { label: '현황판', path: '/dashboard', icon: SquaresFour },
  { label: '고객사', path: '/clients', icon: Buildings },
  { label: '이슈', path: '/issues', icon: Kanban },
  { label: '일정', path: '/calendar', icon: CalendarDots },
]

export function BottomNav() {
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 flex border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] lg:hidden"
      aria-label="하단 탭"
    >
      {TABS.map((tab) => (
        <NavLink
          key={tab.path}
          to={tab.path}
          className={({ isActive }) =>
            `flex min-h-[44px] flex-1 flex-col items-center justify-center gap-0.5 py-2 text-[11px] ${
              isActive ? 'font-semibold text-slate-900' : 'text-slate-400'
            }`
          }
        >
          {({ isActive }) => (
            <>
              <tab.icon size={20} weight={isActive ? 'fill' : 'regular'} />
              {tab.label}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
