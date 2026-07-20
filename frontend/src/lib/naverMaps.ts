// Naver Maps JS API v3 동적 로더 — SCR-09 지도 공급자 추가 (구글과 병행)
// googleMaps.ts 의 최소 표면(GoogleMapsApi)을 그대로 구현하는 어댑터를 반환해
// MapPage 가 공급자와 무관하게 동일 코드로 동작한다.
// 키: VITE_NAVER_MAPS_CLIENT_ID (NCP Maps Application 의 Client ID, 도메인 등록 필요)

import {
  MapsKeyMissingError,
  MapsLoadError,
  type GInfoWindow,
  type GLatLngBounds,
  type GLatLngLiteral,
  type GMap,
  type GMarker,
  type GoogleMapsApi,
} from './googleMaps'

// ── naver.maps 원시 표면 (사용하는 부분만 선언 — 신규 의존성 금지) ──────
interface NLatLng {
  readonly __brand?: 'NLatLng'
}

interface NMap {
  setCenter(center: NLatLng): void
  setZoom(zoom: number): void
  fitBounds(bounds: unknown, margin?: number): void
}

interface NMarker {
  setMap(map: NMap | null): void
}

interface NInfoWindow {
  setContent(content: string | HTMLElement): void
  open(map: NMap, anchor: NMarker): void
  close(): void
}

interface NBounds {
  extend(point: NLatLng): void
}

interface NaverMapsApi {
  Map: new (el: HTMLElement, opts?: Record<string, unknown>) => NMap
  Marker: new (opts?: Record<string, unknown>) => NMarker
  InfoWindow: new (opts?: Record<string, unknown>) => NInfoWindow
  LatLngBounds: new (sw: NLatLng, ne: NLatLng) => NBounds
  LatLng: new (lat: number, lng: number) => NLatLng
  Point: new (x: number, y: number) => unknown
  Event: {
    addListener(target: unknown, eventName: string, handler: () => void): unknown
    removeListener(listener: unknown): void
  }
}

declare global {
  interface Window {
    naver?: { maps?: NaverMapsApi }
    /** Naver Maps 인증 실패 전역 훅 (잘못된 Client ID·도메인 미등록 등) */
    navermap_authFailure?: () => void
  }
}

/** 인증 실패가 로드 완료 후 비동기로 도착할 때 발행되는 이벤트 (구글의 gmaps:auth-failure 대응) */
export const NAVER_MAPS_AUTH_FAILURE_EVENT = 'nmaps:auth-failure'

export function getNaverMapsKey(): string | undefined {
  const key = import.meta.env.VITE_NAVER_MAPS_CLIENT_ID as string | undefined
  const trimmed = key?.trim()
  return trimmed ? trimmed : undefined
}

// ── GoogleMapsApi 표면 어댑터 ────────────────────────────────────────
class NaverBoundsAdapter implements GLatLngBounds {
  // 네이버 LatLngBounds 는 빈 생성자 시 NaN bounds 가 되어 extend 가 영구 실패한다
  // (sw/ne 필수) — 첫 점이 들어올 때 그 점으로 초기화하는 지연 생성으로 우회.
  raw: NBounds | null = null
  constructor(private n: NaverMapsApi) {}
  extend(point: GLatLngLiteral): void {
    const latLng = new this.n.LatLng(point.lat, point.lng)
    if (this.raw) {
      this.raw.extend(latLng)
    } else {
      this.raw = new this.n.LatLngBounds(latLng, latLng)
    }
  }
}

class NaverMapAdapter implements GMap {
  raw: NMap
  constructor(
    private n: NaverMapsApi,
    el: HTMLElement,
    opts?: Record<string, unknown>,
  ) {
    // 구글 전용 옵션(styles·streetViewControl 등)은 버리고 공통 옵션만 번역
    const center = opts?.center as GLatLngLiteral | undefined
    this.raw = new n.Map(el, {
      ...(center ? { center: new n.LatLng(center.lat, center.lng) } : {}),
      ...(typeof opts?.zoom === 'number' ? { zoom: opts.zoom } : {}),
      mapTypeControl: false,
    })
  }
  setCenter(center: GLatLngLiteral): void {
    this.raw.setCenter(new this.n.LatLng(center.lat, center.lng))
  }
  setZoom(zoom: number): void {
    this.raw.setZoom(zoom)
  }
  fitBounds(bounds: GLatLngBounds, padding?: number): void {
    const raw = (bounds as NaverBoundsAdapter).raw
    if (raw) this.raw.fitBounds(raw, padding) // 점이 없는 bounds 는 무시 (호출부는 2점 이상에서만 사용)
  }
}

interface GCircleIcon {
  path?: number
  scale?: number
  fillColor?: string
  fillOpacity?: number
  strokeColor?: string
  strokeWeight?: number
}

class NaverMarkerAdapter implements GMarker {
  raw: NMarker
  constructor(
    private n: NaverMapsApi,
    opts?: Record<string, unknown>,
  ) {
    const position = opts?.position as GLatLngLiteral | undefined
    const map = opts?.map as NaverMapAdapter | undefined
    const icon = opts?.icon as GCircleIcon | undefined

    const translated: Record<string, unknown> = {
      ...(position ? { position: new n.LatLng(position.lat, position.lng) } : {}),
      ...(map ? { map: map.raw } : {}),
      ...(typeof opts?.title === 'string' ? { title: opts.title } : {}),
    }
    // 구글 SymbolPath.CIRCLE 아이콘 → HTML 원형 마커로 번역 (지도 화면의 유일한 아이콘 형태)
    if (icon && typeof icon.scale === 'number') {
      const size = icon.scale * 2
      translated.icon = {
        content:
          `<span style="display:block;width:${size}px;height:${size}px;border-radius:50%;` +
          `background:${icon.fillColor ?? '#10b981'};` +
          `border:${icon.strokeWeight ?? 2}px solid ${icon.strokeColor ?? '#ffffff'};` +
          'box-sizing:border-box;box-shadow:0 1px 3px rgba(0,0,0,.35);"></span>',
        anchor: new n.Point(size / 2, size / 2),
      }
    }
    this.raw = new n.Marker(translated)
  }
  setMap(map: GMap | null): void {
    this.raw.setMap(map ? (map as NaverMapAdapter).raw : null)
  }
  addListener(eventName: string, handler: () => void): { remove(): void } {
    const listener = this.n.Event.addListener(this.raw, eventName, handler)
    return { remove: () => this.n.Event.removeListener(listener) }
  }
}

class NaverInfoWindowAdapter implements GInfoWindow {
  private raw: NInfoWindow
  constructor(n: NaverMapsApi, opts?: Record<string, unknown>) {
    this.raw = new n.InfoWindow({
      content: '',
      borderWidth: 0,
      backgroundColor: '#ffffff',
      anchorSize: { width: 12, height: 10 },
      ...(opts ?? {}),
    })
  }
  setContent(content: string | HTMLElement): void {
    this.raw.setContent(content)
  }
  open(options: { map: GMap; anchor: GMarker }): void {
    this.raw.open((options.map as NaverMapAdapter).raw, (options.anchor as NaverMarkerAdapter).raw)
  }
  close(): void {
    this.raw.close()
  }
}

function adapt(n: NaverMapsApi): GoogleMapsApi {
  return {
    Map: class {
      constructor(el: HTMLElement, opts?: Record<string, unknown>) {
        return new NaverMapAdapter(n, el, opts)
      }
    } as unknown as GoogleMapsApi['Map'],
    Marker: class {
      constructor(opts?: Record<string, unknown>) {
        return new NaverMarkerAdapter(n, opts)
      }
    } as unknown as GoogleMapsApi['Marker'],
    InfoWindow: class {
      constructor(opts?: Record<string, unknown>) {
        return new NaverInfoWindowAdapter(n, opts)
      }
    } as unknown as GoogleMapsApi['InfoWindow'],
    LatLngBounds: class {
      constructor() {
        return new NaverBoundsAdapter(n)
      }
    } as unknown as GoogleMapsApi['LatLngBounds'],
    SymbolPath: { CIRCLE: 0 },
  }
}

let loadPromise: Promise<GoogleMapsApi> | null = null
let adapted: GoogleMapsApi | null = null
// 네이버 스크립트는 인증 실패해도 전역 naver.maps 가 남는다 — 실패를 기억해
// 재시도 시 "가짜 ready"(타일 차단된 깨진 지도)로 빠지지 않게 한다. 복구는 새로고침.
let authFailed = false

/** Naver Maps JS API 로드 — 중복 호출 시 동일 Promise 재사용, 실패 시 재시도 가능 */
export function loadNaverMaps(): Promise<GoogleMapsApi> {
  if (authFailed) return Promise.reject(new MapsLoadError('AUTH'))
  const existing = window.naver?.maps
  if (existing?.Map) {
    adapted = adapted ?? adapt(existing)
    return Promise.resolve(adapted)
  }
  if (loadPromise) return loadPromise

  const key = getNaverMapsKey()
  if (!key) return Promise.reject(new MapsKeyMissingError())

  loadPromise = new Promise<GoogleMapsApi>((resolve, reject) => {
    const script = document.createElement('script')

    const fail = (reason: 'NETWORK' | 'INIT' | 'AUTH') => {
      loadPromise = null // 실패 시 재시도 허용
      script.remove()
      reject(new MapsLoadError(reason))
    }

    // 잘못된 Client ID·도메인 미등록 — 로드 전이면 reject, 로드 후면 이벤트로 통지
    window.navermap_authFailure = () => {
      authFailed = true
      window.dispatchEvent(new CustomEvent(NAVER_MAPS_AUTH_FAILURE_EVENT))
      fail('AUTH')
    }

    script.src = `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=${encodeURIComponent(key)}`
    script.async = true
    script.defer = true
    script.onload = () => {
      const maps = window.naver?.maps
      if (maps?.Map) {
        adapted = adapted ?? adapt(maps)
        resolve(adapted)
      } else {
        fail('INIT')
      }
    }
    script.onerror = () => fail('NETWORK')
    document.head.appendChild(script)
  })

  return loadPromise
}
