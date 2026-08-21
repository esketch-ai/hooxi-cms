// 허브 서브탭(A안) — LNB에서 하나로 접힌 허브(재무 관리·자산 관리)의 화면 상단 탭 전환.
// 현재 경로가 속한 허브를 찾아 '표시 가능한' 소속 화면들만 탭으로 렌더한다.
// 필터 규칙은 Sidebar와 동일(재무 OFF·role·OBSERVER·그룹 허용) — 탭도 권한 경계를 지킨다.
// 탭이 1개뿐이면(=혼자 남음) 렌더하지 않는다.
import { NavLink, useLocation } from 'react-router-dom'
import { useAuth } from '../app/AuthProvider'
import { NAV_GROUPS, NAV_HUBS, type NavItem } from '../layouts/AppShell/nav'
import { isObserverAllowed } from '../layouts/AppShell/observerAccess'
import { FINANCE_FEATURES, isFinanceHiddenPath } from '../lib/featureFlags'
import { isMenuAllowed } from '../lib/menuAccess'

const ITEM_BY_PATH: Record<string, NavItem> = Object.fromEntries(
  NAV_GROUPS.flatMap((g) => g.items.map((i) => [i.path, i])),
)

export function SectionTabs() {
  const { pathname } = useLocation()
  const { user } = useAuth()

  const hub = NAV_HUBS.find((h) =>
    h.paths.some((p) => pathname === p || pathname.startsWith(`${p}/`)),
  )
  if (!hub) return null

  const isObserver = user?.role === 'OBSERVER'
  const tabs = hub.paths
    .map((p) => ITEM_BY_PATH[p])
    .filter((item): item is NavItem => !!item)
    .filter(
      (item) =>
        (FINANCE_FEATURES || !isFinanceHiddenPath(item.path)) &&
        (!item.roles || (user && item.roles.includes(user.role))) &&
        (!isObserver || isObserverAllowed(item.path)) &&
        isMenuAllowed(user, item.path),
    )
  if (tabs.length < 2) return null

  return (
    <div className="flex gap-1 overflow-x-auto border-b border-hairline" role="tablist">
      {tabs.map((t) => (
        <NavLink
          key={t.path}
          to={t.path}
          className={({ isActive }) =>
            `flex shrink-0 items-center gap-1.5 border-b-2 px-3.5 py-2.5 text-sm font-medium transition-colors ${
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
    </div>
  )
}
