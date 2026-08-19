// OBSERVER(경영 관찰) 격리 — nav 필터와 라우트 가드가 공유하는 단일 화이트리스트.
// OBSERVER는 아래 경로(및 그 하위)만 접근 가능하고, 밖으로 나가면 홈으로 리다이렉트한다.
// 기존 내부 3역할(STAFF/MANAGER/ADMIN)·외부 포털 역할에는 영향 없음(회귀 0).
import { FINANCE_FEATURES } from '../../lib/featureFlags'

// ON(기존): 경영 관찰·재무 원장·자산관리 보고 중심. 홈은 /observe.
export const OBSERVER_PATHS_ON = ['/observe', '/finance-ledger', '/asset-report', '/asset-vehicles', '/guide']
// OFF(재무 은닉): /observe·/finance-ledger·/asset-report 라우트가 사라지므로 유효 경로만 남긴다.
// 홈은 /dashboard(유효 경로) — 리다이렉트 무한루프 방지.
export const OBSERVER_PATHS_OFF = ['/dashboard', '/asset-vehicles', '/guide']

/** 재무 플래그에 따른 OBSERVER 화이트리스트 */
export function observerPaths(financeEnabled: boolean): string[] {
  return financeEnabled ? OBSERVER_PATHS_ON : OBSERVER_PATHS_OFF
}

/** 재무 플래그에 따른 OBSERVER 기본 랜딩(화이트리스트 밖 접근 시 되돌아갈 유효 경로) */
export function observerHome(financeEnabled: boolean): string {
  return financeEnabled ? '/observe' : '/dashboard'
}

/** pathname이 OBSERVER 화이트리스트에 속하는지 — 정확 매칭 우선, 상세 경로는 하위 매칭 허용 */
export function isObserverAllowed(pathname: string, financeEnabled: boolean = FINANCE_FEATURES): boolean {
  return observerPaths(financeEnabled).some(
    (base) => pathname === base || pathname.startsWith(`${base}/`),
  )
}

// 현재 빌드 플래그 기준 상수(기존 공개 API 유지) — ON이면 종전 값과 동일.
export const OBSERVER_PATHS = observerPaths(FINANCE_FEATURES)
/** OBSERVER 기본 랜딩(화이트리스트 밖 접근 시 되돌아갈 화면) */
export const OBSERVER_HOME = observerHome(FINANCE_FEATURES)
