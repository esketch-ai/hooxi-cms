// OBSERVER(경영 관찰) 격리 — nav 필터와 라우트 가드가 공유하는 단일 화이트리스트.
// OBSERVER는 아래 경로(및 그 하위)만 접근 가능하고, 밖으로 나가면 /observe로 리다이렉트한다.
// 기존 내부 3역할(STAFF/MANAGER/ADMIN)·외부 포털 역할에는 영향 없음(회귀 0).
export const OBSERVER_PATHS = ['/observe', '/finance-ledger', '/asset-report', '/asset-vehicles', '/guide']

/** OBSERVER 기본 랜딩(화이트리스트 밖 접근 시 되돌아갈 경영 관찰 화면) */
export const OBSERVER_HOME = '/observe'

/** pathname이 OBSERVER 화이트리스트에 속하는지 — 정확 매칭 우선, 상세 경로는 하위 매칭 허용 */
export function isObserverAllowed(pathname: string): boolean {
  return OBSERVER_PATHS.some(
    (base) => pathname === base || pathname.startsWith(`${base}/`),
  )
}
