// Google Maps JS API 동적 로더 — SCR-09 (플랜 §10.4: 키는 VITE_GOOGLE_MAPS_KEY 환경변수)
// npm 의존성 추가 금지 → script 태그 삽입 방식. 중복 로드 방지 · 실패/키 미설정 처리.

/** 최소 타입 정의 — @types/google.maps 미사용(신규 의존성 금지), 사용하는 표면만 선언 */
export interface GLatLngLiteral {
  lat: number
  lng: number
}

export interface GLatLngBounds {
  extend(point: GLatLngLiteral): void
}

export interface GMap {
  setCenter(center: GLatLngLiteral): void
  setZoom(zoom: number): void
  fitBounds(bounds: GLatLngBounds, padding?: number): void
}

export interface GMarker {
  setMap(map: GMap | null): void
  addListener(eventName: string, handler: () => void): { remove(): void }
}

export interface GInfoWindow {
  setContent(content: string | HTMLElement): void
  open(options: { map: GMap; anchor: GMarker }): void
  close(): void
}

export interface GoogleMapsApi {
  Map: new (el: HTMLElement, opts?: Record<string, unknown>) => GMap
  Marker: new (opts?: Record<string, unknown>) => GMarker
  InfoWindow: new (opts?: Record<string, unknown>) => GInfoWindow
  LatLngBounds: new () => GLatLngBounds
  SymbolPath: { CIRCLE: number }
}

declare global {
  interface Window {
    google?: { maps?: GoogleMapsApi }
    /** Google Maps 인증 실패 전역 훅 (잘못된 키·리퍼러 제한 등) */
    gm_authFailure?: () => void
  }
}

/** VITE_GOOGLE_MAPS_KEY 미설정 */
export class MapsKeyMissingError extends Error {
  constructor() {
    super('VITE_GOOGLE_MAPS_KEY가 설정되지 않았습니다')
    this.name = 'MapsKeyMissingError'
  }
}

/** 네트워크·초기화·인증 실패 */
export class MapsLoadError extends Error {
  constructor(public reason: 'NETWORK' | 'INIT' | 'AUTH') {
    super(`Google Maps 로드 실패 (${reason})`)
    this.name = 'MapsLoadError'
  }
}

/** 인증 실패(gm_authFailure)가 로드 완료 후 비동기로 도착할 때 발행되는 이벤트 */
export const MAPS_AUTH_FAILURE_EVENT = 'gmaps:auth-failure'

export function getMapsKey(): string | undefined {
  const key = import.meta.env.VITE_GOOGLE_MAPS_KEY as string | undefined
  const trimmed = key?.trim()
  return trimmed ? trimmed : undefined
}

let loadPromise: Promise<GoogleMapsApi> | null = null

/** Google Maps JS API 로드 — 중복 호출 시 동일 Promise 재사용, 실패 시 재시도 가능 */
export function loadGoogleMaps(): Promise<GoogleMapsApi> {
  const existing = window.google?.maps
  if (existing?.Map) return Promise.resolve(existing)
  if (loadPromise) return loadPromise

  const key = getMapsKey()
  if (!key) return Promise.reject(new MapsKeyMissingError())

  loadPromise = new Promise<GoogleMapsApi>((resolve, reject) => {
    const script = document.createElement('script')

    const fail = (reason: 'NETWORK' | 'INIT' | 'AUTH') => {
      loadPromise = null // 실패 시 재시도 허용
      script.remove()
      reject(new MapsLoadError(reason))
    }

    // 잘못된 키·리퍼러 제한 등 — 로드 전이면 reject, 로드 후면 이벤트로 통지
    window.gm_authFailure = () => {
      window.dispatchEvent(new CustomEvent(MAPS_AUTH_FAILURE_EVENT))
      fail('AUTH')
    }

    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&language=ko&region=KR`
    script.async = true
    script.defer = true
    script.onload = () => {
      const maps = window.google?.maps
      if (maps?.Map) resolve(maps)
      else fail('INIT')
    }
    script.onerror = () => fail('NETWORK')
    document.head.appendChild(script)
  })

  return loadPromise
}
