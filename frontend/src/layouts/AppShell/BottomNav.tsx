// 모바일 하단 탭 바: 현황판·고객사·이슈·일정·상담 (플랜 §7 / 01_COMMON §6 + SCR-08 뱃지)
import { NavLink } from 'react-router-dom'
import {
  Buildings,
  CalendarDots,
  ChatCircleDots,
  Kanban,
  SquaresFour,
} from '@phosphor-icons/react'
import { useChatBadge } from '../../lib/api/queries'
import type { NavItem } from './nav'

const TABS: Pick<NavItem, 'label' | 'path' | 'icon' | 'badgeKey'>[] = [
  { label: '현황판', path: '/dashboard', icon: SquaresFour },
  { label: '고객사', path: '/clients', icon: Buildings },
  { label: '이슈', path: '/issues', icon: Kanban },
  { label: '일정', path: '/calendar', icon: CalendarDots },
  { label: '상담', path: '/chat', icon: ChatCircleDots, badgeKey: 'chat' },
]

export function BottomNav() {
  const { data: chatBadge } = useChatBadge()
  const waiting = chatBadge?.waiting ?? 0

  return (
    <nav
      className="fixed inset-x-4 bottom-[calc(1rem+env(safe-area-inset-bottom))] z-40 flex overflow-hidden rounded-[24px] border border-hairline bg-graphite/90 backdrop-blur lg:hidden"
      aria-label="하단 탭"
    >
      {TABS.map((tab) => (
        <NavLink
          key={tab.path}
          to={tab.path}
          className={({ isActive }) =>
            `flex min-h-[44px] flex-1 flex-col items-center justify-center gap-0.5 py-2 text-[11px] transition-colors ${
              isActive ? 'font-semibold text-bone' : 'text-slatey'
            }`
          }
        >
          {({ isActive }) => (
            <>
              <span className="relative">
                <tab.icon size={20} weight={isActive ? 'fill' : 'regular'} />
                {tab.badgeKey === 'chat' && waiting > 0 && (
                  <span className="absolute -top-1.5 -right-2.5 inline-flex min-w-[16px] items-center justify-center rounded-full bg-rose-500 px-1 py-px text-[9px] font-bold text-white">
                    {waiting > 99 ? '99+' : waiting}
                  </span>
                )}
              </span>
              {tab.label}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
