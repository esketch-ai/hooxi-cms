// Kakao Maps JS SDK 동적 로더 — SCR-09 지도 공급자 추가 (구글·네이버와 병행)
// googleMaps.ts 의 최소 표면(GoogleMapsApi)을 그대로 구현하는 어댑터를 반환해
// MapPage 가 공급자와 무관하게 동일 코드로 동작한다.
// 키: VITE_KAKAO_MAPS_JS_KEY (카카오 개발자 앱의 JavaScript 키, 플랫폼 Web 도메인 등록 필요)
// 주의: REST 키(지오코딩용)와 다른 'JavaScript 키'다.

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

// ── kakao.maps 원시 표면 (사용하는 부분만 선언 — 신규 의존성 금지) ──────
interface KLatLng {
  readonly __brand?: 'KLatLng'
}

interface KMap {
  setCenter(latlng: KLatLng): void
  setLevel(level: number): void
  setBounds(bounds: KBounds, pt?: number, pr?: number, pb?: number, pl?: number): void
}

interface KMarker {
  setMap(map: KMap | null): void
}

interface KInfoWindow {
  setContent(content: string | HTMLElement): void
  open(map: KMap, marker: KMarker): void
  close(): void
}

interface KBounds {
  extend(latlng: KLatLng): void
}

interface KakaoMapsApi {
  Map: new (el: HTMLElement, opts: Record<string, unknown>) => KMap
  Marker: new (opts?: Record<string, unknown>) => KMarker
  InfoWindow: new (opts?: Record<string, unknown>) => KInfoWindow
  LatLngBounds: new () => KBounds
  LatLng: new (lat: number, lng: number) => KLatLng
  Size: new (w: number, h: number) => unknown
  Point: new (x: number, y: number) => unknown
  MarkerImage: new (src: string, size: unknown, opts?: Record<string, unknown>) => unknown
  event: {
    addListener(target: unknown, type: string, handler: () => void): void
    removeListener(target: unknown, type: string, handler: () => void): void
  }
}

declare global {
  interface Window {
    kakao?: {
      maps?: KakaoMapsApi & { load?: (cb: () => void) => void }
    }
  }
}

/** 인증 실패 이벤트(구글·네이버 대응) — 카카오 SDK엔 전역 authFailure 훅이 없어 실질적으로
 * 발행되지 않지만, MapPage의 공급자별 이벤트 구독 스위치 대칭을 위해 상수만 노출한다. */
export const KAKAO_MAPS_AUTH_FAILURE_EVENT = 'kmaps:auth-failure'

export function getKakaoMapsKey(): string | undefined {
  const key = import.meta.env.VITE_KAKAO_MAPS_JS_KEY as string | undefined
  const trimmed = key?.trim()
  return trimmed ? trimmed : undefined
}

/** 구글 zoom → 카카오 level 근사 변환 (카카오는 level이 작을수록 확대, 1~14).
 * 관제 지도가 쓰는 값 기준 보정: zoom 7(전국)→level 13, zoom 11(단일)→level 9. */
function zoomToLevel(zoom: number): number {
  return Math.max(1, Math.min(14, Math.round(20 - zoom)))
}

// ── GoogleMapsApi 표면 어댑터 ────────────────────────────────────────
class KakaoBoundsAdapter implements GLatLngBounds {
  raw: KBounds
  constructor(private k: KakaoMapsApi) {
    this.raw = new k.LatLngBounds()
  }
  extend(point: GLatLngLiteral): void {
    this.raw.extend(new this.k.LatLng(point.lat, point.lng))
  }
}

class KakaoMapAdapter implements GMap {
  raw: KMap
  constructor(
    private k: KakaoMapsApi,
    el: HTMLElement,
    opts?: Record<string, unknown>,
  ) {
    // 구글 전용 옵션(styles·streetViewControl 등)은 버리고 공통 옵션만 번역
    const center = opts?.center as GLatLngLiteral | undefined
    const zoom = typeof opts?.zoom === 'number' ? opts.zoom : 7
    this.raw = new k.Map(el, {
      center: new k.LatLng(center?.lat ?? 36.5, center?.lng ?? 127.8),
      level: zoomToLevel(zoom),
    })
  }
  setCenter(center: GLatLngLiteral): void {
    this.raw.setCenter(new this.k.LatLng(center.lat, center.lng))
  }
  setZoom(zoom: number): void {
    this.raw.setLevel(zoomToLevel(zoom))
  }
  fitBounds(bounds: GLatLngBounds, padding?: number): void {
    const raw = (bounds as KakaoBoundsAdapter).raw
    const p = padding ?? 0
    this.raw.setBounds(raw, p, p, p, p)
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

class KakaoMarkerAdapter implements GMarker {
  raw: KMarker
  constructor(
    private k: KakaoMapsApi,
    opts?: Record<string, unknown>,
  ) {
    const position = opts?.position as GLatLngLiteral | undefined
    const map = opts?.map as KakaoMapAdapter | undefined
    const icon = opts?.icon as GCircleIcon | undefined

    const translated: Record<string, unknown> = {
      ...(position ? { position: new k.LatLng(position.lat, position.lng) } : {}),
      ...(map ? { map: map.raw } : {}),
      ...(typeof opts?.title === 'string' ? { title: opts.title } : {}),
    }
    // 구글 SymbolPath.CIRCLE 아이콘 → SVG data URI 원형 MarkerImage 로 번역
    if (icon && typeof icon.scale === 'number') {
      const size = icon.scale * 2
      const sw = icon.strokeWeight ?? 2
      const r = size / 2 - sw
      const svg =
        `<svg xmlns='http://www.w3.org/2000/svg' width='${size}' height='${size}'>` +
        `<circle cx='${size / 2}' cy='${size / 2}' r='${r}' ` +
        `fill='${icon.fillColor ?? '#10b981'}' stroke='${icon.strokeColor ?? '#ffffff'}' stroke-width='${sw}'/></svg>`
      const src = 'data:image/svg+xml,' + encodeURIComponent(svg)
      translated.image = new k.MarkerImage(src, new k.Size(size, size), {
        offset: new k.Point(size / 2, size / 2),
      })
    }
    this.raw = new k.Marker(translated)
  }
  setMap(map: GMap | null): void {
    this.raw.setMap(map ? (map as KakaoMapAdapter).raw : null)
  }
  addListener(eventName: string, handler: () => void): { remove(): void } {
    this.k.event.addListener(this.raw, eventName, handler)
    return { remove: () => this.k.event.removeListener(this.raw, eventName, handler) }
  }
}

class KakaoInfoWindowAdapter implements GInfoWindow {
  private raw: KInfoWindow
  constructor(k: KakaoMapsApi) {
    this.raw = new k.InfoWindow({ removable: false })
  }
  setContent(content: string | HTMLElement): void {
    this.raw.setContent(content)
  }
  open(options: { map: GMap; anchor: GMarker }): void {
    this.raw.open((options.map as KakaoMapAdapter).raw, (options.anchor as KakaoMarkerAdapter).raw)
  }
  close(): void {
    this.raw.close()
  }
}

function adapt(k: KakaoMapsApi): GoogleMapsApi {
  return {
    Map: class {
      constructor(el: HTMLElement, opts?: Record<string, unknown>) {
        return new KakaoMapAdapter(k, el, opts)
      }
    } as unknown as GoogleMapsApi['Map'],
    Marker: class {
      constructor(opts?: Record<string, unknown>) {
        return new KakaoMarkerAdapter(k, opts)
      }
    } as unknown as GoogleMapsApi['Marker'],
    InfoWindow: class {
      constructor() {
        return new KakaoInfoWindowAdapter(k)
      }
    } as unknown as GoogleMapsApi['InfoWindow'],
    LatLngBounds: class {
      constructor() {
        return new KakaoBoundsAdapter(k)
      }
    } as unknown as GoogleMapsApi['LatLngBounds'],
    SymbolPath: { CIRCLE: 0 },
  }
}

let loadPromise: Promise<GoogleMapsApi> | null = null
let adapted: GoogleMapsApi | null = null

/** Kakao Maps JS SDK 로드 — 중복 호출 시 동일 Promise 재사용, 실패 시 재시도 가능 */
export function loadKakaoMaps(): Promise<GoogleMapsApi> {
  const existing = window.kakao?.maps
  if (existing?.Map) {
    adapted = adapted ?? adapt(existing as KakaoMapsApi)
    return Promise.resolve(adapted)
  }
  if (loadPromise) return loadPromise

  const key = getKakaoMapsKey()
  if (!key) return Promise.reject(new MapsKeyMissingError())

  loadPromise = new Promise<GoogleMapsApi>((resolve, reject) => {
    const script = document.createElement('script')

    const fail = (reason: 'NETWORK' | 'INIT' | 'AUTH') => {
      loadPromise = null // 실패 시 재시도 허용
      script.remove()
      reject(new MapsLoadError(reason))
    }

    // autoload=false → onload 후 kakao.maps.load(cb)로 실제 모듈 초기화 완료 시점에 resolve
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(key)}&autoload=false`
    script.async = true
    script.defer = true
    script.onload = () => {
      const loader = window.kakao?.maps?.load
      if (typeof loader !== 'function') {
        fail('INIT')
        return
      }
      loader(() => {
        const maps = window.kakao?.maps
        if (maps?.Map) {
          adapted = adapted ?? adapt(maps as KakaoMapsApi)
          resolve(adapted)
        } else {
          fail('INIT')
        }
      })
    }
    script.onerror = () => fail('NETWORK')
    document.head.appendChild(script)
  })

  return loadPromise
}
