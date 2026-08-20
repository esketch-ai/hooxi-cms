// 그룹 메뉴 접근(G4) — enforce 모드일 때만 프론트 메뉴 필터·라우트 가드를 적용한다.
// off: 무동작(회귀 0) / monitor: 백엔드 감사로그만(자연 사용 패턴 관찰을 위해 UI 불변).
// ADMIN은 전역 우회, OBSERVER는 기존 observerAccess 화이트리스트가 별도로 적용된다.
// 진짜 차단은 백엔드(access_control.check_request_access) — 여기는 UX 계층이다.
import type { User } from '../types'

/** 메뉴(nav 항목) 하나가 이 사용자에게 허용되는가 — Sidebar/BottomNav 필터용 */
export function isMenuAllowed(user: User | null | undefined, menuPath: string): boolean {
  if (!user) return true
  if (user.role === 'ADMIN' || user.role === 'OBSERVER') return true
  if (user.access_mode !== 'enforce') return true
  const allowed = user.allowed_menus
  if (!allowed || allowed.length === 0) return true // 데이터 없음 — fail-safe(개방)
  return allowed.includes(menuPath)
}

/**
 * 라우트 가드용 — pathname이 속한 메뉴 base를 찾아 허용 여부 판정.
 * 메뉴 정본에 없는 경로(/map, /login 등)는 게이트 대상이 아니므로 허용.
 */
export function isPathAllowedForUser(
  user: User | null | undefined,
  pathname: string,
  menuPaths: string[],
): boolean {
  const base = menuPaths.find((b) => pathname === b || pathname.startsWith(`${b}/`))
  if (!base) return true
  return isMenuAllowed(user, base)
}

/**
 * enforce에서의 로그인 홈 — 그룹 home_path(허용 메뉴 안일 때).
 * home이 비허용이면 /dashboard, 그것도 비허용이면 첫 허용 메뉴로 —
 * 가드(비허용 → groupHome 리다이렉트)와 조합될 때 무한 루프가 나지 않게
 * 반환 경로는 반드시 '허용된' 경로여야 한다.
 */
export function groupHome(user: User | null | undefined): string {
  if (!user || user.access_mode !== 'enforce') return '/dashboard'
  const home = user.home_path || '/dashboard'
  if (isMenuAllowed(user, home)) return home
  if (isMenuAllowed(user, '/dashboard')) return '/dashboard'
  return user.allowed_menus?.[0] ?? '/dashboard'
}
