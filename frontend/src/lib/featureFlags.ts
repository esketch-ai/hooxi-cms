// 빌드타임 기능 플래그 — 배포 대상별로 특정 기능군을 은닉한다(런타임 토글 아님).
// 원칙: 미설정/'off' 이외의 값은 모두 ON(전체 노출). 오직 'off' 일 때만 은닉한다.
//   → 개발/기존 배포는 플래그 미설정이므로 기존 동작이 완전히 보존된다.

/**
 * 재무·정산·자산관리 기능군 노출 여부.
 * `VITE_FEATURE_FINANCE=off` 로 빌드할 때만 OFF(은닉), 그 외에는 ON(기존 전체 노출).
 */
export const FINANCE_FEATURES = import.meta.env.VITE_FEATURE_FINANCE !== 'off'

/**
 * 외부 파트너 포털 노출 여부 — 재무와 분리된 플래그.
 * 재무 ON이면 항상 ON(기존 동작 보존). 재무 OFF 빌드에서도 `VITE_FEATURE_PORTAL=on`이면
 * 포털 서브트리(/portal*)와 발급 화면(/portal-accounts)만 켠다(운영: 재무 은닉 + 포털 개방).
 */
export const PORTAL_FEATURES =
  FINANCE_FEATURES || import.meta.env.VITE_FEATURE_PORTAL === 'on'

/**
 * OFF(은닉) 시 내부 라우트/네비에서 감출 경로 6종(정확 매칭 + 하위 경로).
 * 외부 포털 서브트리(/portal*)는 라우터에서 별도(서브트리 통째 제외)로 처리한다.
 */
export const FINANCE_HIDDEN_PATHS = [
  '/finance-ledger',
  '/asset-report',
  '/settlements',
  '/observe',
  '/buyers',
  '/portal-accounts',
  '/tax-invoices',
] as const

/** pathname이 재무 은닉 대상인지 — 정확 매칭 우선, 하위 경로(startsWith 경계 '/')만 허용.
 *  portalEnabled(기본: 빌드 플래그)면 발급 화면(/portal-accounts)은 은닉에서 제외한다. */
export function isFinanceHiddenPath(
  pathname: string,
  portalEnabled: boolean = PORTAL_FEATURES,
): boolean {
  if (
    portalEnabled &&
    (pathname === '/portal-accounts' || pathname.startsWith('/portal-accounts/'))
  ) {
    return false
  }
  return FINANCE_HIDDEN_PATHS.some(
    (base) => pathname === base || pathname.startsWith(`${base}/`),
  )
}

/**
 * 라우트 노드 배열에서 재무 은닉 경로를 제거하는 순수 필터.
 * financeEnabled=true(ON)면 원본을 그대로 반환(회귀 0), OFF면 은닉 경로만 걸러낸다.
 */
export function filterFinanceRoutes<T extends { path?: string }>(
  routes: T[],
  financeEnabled: boolean,
  portalEnabled: boolean = PORTAL_FEATURES,
): T[] {
  if (financeEnabled) return routes
  return routes.filter((r) => !(r.path && isFinanceHiddenPath(r.path, portalEnabled)))
}

/** 외부 포털(/portal*) 서브트리 노출 여부 — 재무와 분리(PORTAL_FEATURES). */
export function includePortalRoutes(): boolean {
  return PORTAL_FEATURES
}
