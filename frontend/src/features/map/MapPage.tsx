// SCR-09 전국 관제 지도 /map — P3 (SCREEN_DESIGN_PLAN §5)
// 지도 전용 레이아웃 · 좌측 필터(계약 상태 3종 + 최근 활동 기준) · 지역별 집계 · 인포윈도
// 지도 공급자 2종: 구글(VITE_GOOGLE_MAPS_KEY) / 네이버(VITE_NAVER_MAPS_CLIENT_ID) — 우상단 토글 전환
// 키 미설정/로드 실패 시에도 필터·집계 패널은 정상 동작
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Buildings, CircleNotch, MapPinLine, MapTrifold, WarningCircle } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { EmptyState } from '../../components/EmptyState'
import { Skeleton } from '../../components/Skeleton'
import { api } from '../../lib/api/client'
import { unwrapList, useCodes } from '../../lib/api/queries'
import { hexOf } from '../../lib/codePalette'
import { fmtDateTime } from '../../lib/format'
import {
  MAPS_AUTH_FAILURE_EVENT,
  MapsKeyMissingError,
  getMapsKey,
  loadGoogleMaps,
  type GInfoWindow,
  type GMap,
  type GMarker,
  type GoogleMapsApi,
} from '../../lib/googleMaps'
import {
  NAVER_MAPS_AUTH_FAILURE_EVENT,
  getNaverMapsKey,
  loadNaverMaps,
} from '../../lib/naverMaps'
import type { Client, ContractStatus, Paginated } from '../../types'

// ── 지도 공급자 (구글/네이버) — 선택은 localStorage 에 기억 ────────────
type MapProvider = 'google' | 'naver'

const MAP_PROVIDER_STORAGE_KEY = 'hooxi_map_provider'

const PROVIDERS: { id: MapProvider; label: string }[] = [
  { id: 'google', label: '구글' },
  { id: 'naver', label: '네이버' },
]

function readStoredProvider(): MapProvider {
  return localStorage.getItem(MAP_PROVIDER_STORAGE_KEY) === 'naver' ? 'naver' : 'google'
}

function keyOf(provider: MapProvider): string | undefined {
  return provider === 'google' ? getMapsKey() : getNaverMapsKey()
}

// 계약상태 마커 색/라벨은 공통 코드 마스터(CONTRACT_STATUS)에서 파생(컴포넌트 내부).
// 범례·집계는 3개 상태(ACTIVE/HOLD/END) 구조 유지 — 상태 추가 시 지도 확장은 별도 작업.
const STATUS_ORDER: ContractStatus[] = ['ACTIVE', 'HOLD', 'END']

// 코드 미로딩·색상 미지정 시 폴백 hex
const FALLBACK_MARKER_HEX: Record<string, string> = {
  ACTIVE: '#10b981',
  HOLD: '#f59e0b',
  END: '#6b7280',
}

type ContactFilter = '' | 'WITHIN_30' | 'OVER_30'

const KOREA_CENTER = { lat: 36.5, lng: 127.8 }

/** 마지막 활동일 기준 경과 일수 (활동 없음 → null) */
function daysSince(value?: string | null): number | null {
  if (!value) return null
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return null
  return Math.floor((Date.now() - d.getTime()) / 86_400_000)
}

function matchContact(client: Client, filter: ContactFilter): boolean {
  if (!filter) return true
  const days = daysSince(client.last_activity_at)
  if (filter === 'WITHIN_30') return days !== null && days <= 30
  // OVER_30: 30일 초과 활동 없음 — 활동 이력이 아예 없는 곳도 포함
  return days === null || days > 30
}

type MapStatus = 'loading' | 'ready' | 'no-key' | 'error'

export function MapPage() {
  const navigate = useNavigate()
  const { codes: contractCodes } = useCodes('CONTRACT_STATUS')

  // 계약상태 코드 → 마커 색(hex)·표시명 파생. 색 미지정/미로딩은 폴백.
  const MARKER_COLORS = useMemo<Record<string, string>>(() => {
    const m: Record<string, string> = { ...FALLBACK_MARKER_HEX }
    for (const c of contractCodes) if (c.color) m[c.code] = hexOf(c.color)
    return m
  }, [contractCodes])
  const STATUS_LABELS = useMemo<Record<string, string>>(() => {
    const m: Record<string, string> = { ACTIVE: '계약중', HOLD: '보류', END: '종료' }
    for (const c of contractCodes) m[c.code] = c.label
    return m
  }, [contractCodes])

  // ── 데이터: 기존 GET /clients 재사용 (page_size 최대 200) ─────────────
  const {
    data: clients = [],
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['clients', 'map'],
    queryFn: async () => {
      const { data } = await api.get<Client[] | Paginated<Client>>('/clients', {
        params: { page_size: 200 },
      })
      return unwrapList(data).items
    },
  })

  // ── 필터 상태 ────────────────────────────────────────────────────────
  const [statusOn, setStatusOn] = useState<Record<ContractStatus, boolean>>({
    ACTIVE: true,
    HOLD: true,
    END: true,
  })
  const [contactFilter, setContactFilter] = useState<ContactFilter>('')

  const filtered = useMemo(
    () =>
      clients.filter(
        (c) => (statusOn[c.contract_status] ?? true) && matchContact(c, contactFilter),
      ),
    [clients, statusOn, contactFilter],
  )

  const withCoords = useMemo(
    () => filtered.filter((c) => c.lat != null && c.lng != null),
    [filtered],
  )
  const noCoords = useMemo(
    () => filtered.filter((c) => c.lat == null || c.lng == null),
    [filtered],
  )

  // 지역별 집계 (region 기준, 상태 분포 포함)
  const regionAgg = useMemo(() => {
    const map = new Map<string, { total: number } & Record<ContractStatus, number>>()
    filtered.forEach((c) => {
      const region = c.region?.trim() || '지역 미지정'
      const entry = map.get(region) ?? { total: 0, ACTIVE: 0, HOLD: 0, END: 0 }
      entry.total += 1
      entry[c.contract_status] = (entry[c.contract_status] ?? 0) + 1
      map.set(region, entry)
    })
    return Array.from(map.entries()).sort((a, b) => b[1].total - a[1].total)
  }, [filtered])

  const statusCounts = useMemo(() => {
    const counts: Record<ContractStatus, number> = { ACTIVE: 0, HOLD: 0, END: 0 }
    clients.forEach((c) => {
      counts[c.contract_status] = (counts[c.contract_status] ?? 0) + 1
    })
    return counts
  }, [clients])

  // ── 지도 로드·마커 (공급자 전환 가능) ────────────────────────────────
  const [provider, setProvider] = useState<MapProvider>(readStoredProvider)
  const [mapStatus, setMapStatus] = useState<MapStatus>(() =>
    keyOf(readStoredProvider()) ? 'loading' : 'no-key',
  )
  const [retryToken, setRetryToken] = useState(0)
  const mapElRef = useRef<HTMLDivElement>(null)
  const apiRef = useRef<GoogleMapsApi | null>(null)
  const gmapRef = useRef<GMap | null>(null)
  const infoRef = useRef<GInfoWindow | null>(null)
  const markersRef = useRef<GMarker[]>([])

  const switchProvider = (next: MapProvider) => {
    if (next === provider) return
    localStorage.setItem(MAP_PROVIDER_STORAGE_KEY, next)
    // 이전 공급자의 지도·마커 참조 정리 (지도 DOM 은 key={provider} 로 재생성)
    apiRef.current = null
    gmapRef.current = null
    infoRef.current = null
    markersRef.current = []
    // 전환 직후 이전 'ready' 잔상(빈 지도 위 범례) 방지 — 상태를 즉시 갱신
    setMapStatus(keyOf(next) ? 'loading' : 'no-key')
    setProvider(next)
  }

  useEffect(() => {
    if (!keyOf(provider)) {
      setMapStatus('no-key')
      return
    }
    let canceled = false
    setMapStatus('loading')

    ;(provider === 'google' ? loadGoogleMaps() : loadNaverMaps())
      .then((maps) => {
        if (canceled || !mapElRef.current) return
        apiRef.current = maps
        gmapRef.current = new maps.Map(mapElRef.current, {
          center: KOREA_CENTER,
          zoom: 7,
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: false,
          styles: [{ featureType: 'poi', stylers: [{ visibility: 'off' }] }],
        })
        infoRef.current = new maps.InfoWindow()
        setMapStatus('ready')
      })
      .catch((error) => {
        if (canceled) return
        setMapStatus(error instanceof MapsKeyMissingError ? 'no-key' : 'error')
      })

    // 로드 완료 후 비동기 인증 실패 — 활성 공급자의 이벤트만 구독
    // (이전 공급자의 지연 실패가 현재 정상 지도를 'error' 로 오염시키지 않도록)
    const authEvent =
      provider === 'google' ? MAPS_AUTH_FAILURE_EVENT : NAVER_MAPS_AUTH_FAILURE_EVENT
    const onAuthFail = () => {
      if (!canceled) setMapStatus('error')
    }
    window.addEventListener(authEvent, onAuthFail)
    return () => {
      canceled = true
      window.removeEventListener(authEvent, onAuthFail)
    }
  }, [retryToken, provider])

  // 인포윈도 콘텐츠 — innerHTML 대신 DOM 생성(고객사명 이스케이프 + SPA 네비게이션)
  const buildInfoContent = (client: Client): HTMLElement => {
    const root = document.createElement('div')
    root.className = 'min-w-44 max-w-60 p-1'

    const name = document.createElement('p')
    name.className = 'text-sm font-bold text-slate-900'
    name.textContent = client.company_name
    root.appendChild(name)

    const statusRow = document.createElement('p')
    statusRow.className = 'mt-1 flex items-center gap-1.5 text-xs text-slate-600'
    const dot = document.createElement('span')
    dot.className = 'inline-block h-2 w-2 rounded-full'
    dot.style.backgroundColor = MARKER_COLORS[client.contract_status]
    statusRow.appendChild(dot)
    statusRow.appendChild(
      document.createTextNode(
        `${STATUS_LABELS[client.contract_status] ?? client.contract_status}${
          client.region ? ` · ${client.region}` : ''
        }`,
      ),
    )
    root.appendChild(statusRow)

    const activity = document.createElement('p')
    activity.className = 'mt-1 text-xs text-slate-400'
    activity.textContent = client.last_activity_at
      ? `최근 활동 ${fmtDateTime(client.last_activity_at)}`
      : '활동 이력 없음'
    root.appendChild(activity)

    const button = document.createElement('button')
    button.type = 'button'
    button.className =
      'mt-2 w-full rounded-md bg-slate-800 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-slate-700'
    button.textContent = '상세 보기'
    button.addEventListener('click', () => navigate(`/clients/${client.client_id}`))
    root.appendChild(button)

    return root
  }

  // 마커 동기화 — 필터 결과 변경 시 재생성 + fitBounds
  useEffect(() => {
    const maps = apiRef.current
    const gmap = gmapRef.current
    if (mapStatus !== 'ready' || !maps || !gmap) return

    markersRef.current.forEach((m) => m.setMap(null))
    markersRef.current = []
    infoRef.current?.close()

    const bounds = new maps.LatLngBounds()
    withCoords.forEach((client) => {
      const position = { lat: client.lat as number, lng: client.lng as number }
      const marker = new maps.Marker({
        position,
        map: gmap,
        title: client.company_name,
        icon: {
          path: maps.SymbolPath.CIRCLE,
          scale: 9,
          fillColor: MARKER_COLORS[client.contract_status],
          fillOpacity: 1,
          strokeColor: '#ffffff',
          strokeWeight: 2,
        },
      })
      marker.addListener('click', () => {
        const info = infoRef.current
        if (!info) return
        info.setContent(buildInfoContent(client))
        info.open({ map: gmap, anchor: marker })
      })
      bounds.extend(position)
      markersRef.current.push(marker)
    })

    if (withCoords.length > 1) {
      gmap.fitBounds(bounds, 48)
    } else if (withCoords.length === 1) {
      gmap.setCenter({ lat: withCoords[0].lat as number, lng: withCoords[0].lng as number })
      gmap.setZoom(11)
    } else {
      gmap.setCenter(KOREA_CENTER)
      gmap.setZoom(7)
    }
    // buildInfoContent는 navigate만 캡처(안정 참조) — 마커는 필터 결과·지도 준비 상태에만 의존
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapStatus, withCoords])

  // ── 고객사 목록 로드 실패 ────────────────────────────────────────────
  if (isError) {
    return (
      <div className="animate-fade-in space-y-4">
        <PageHeader title="전국 관제 지도" subtitle="고객사 분포·계약 상태 관제" />
        <EmptyState
          icon={<MapTrifold size={36} />}
          title="고객사 데이터를 불러오지 못했습니다"
          description="네트워크 상태를 확인한 뒤 다시 시도해 주세요."
          action={
            <button
              type="button"
              onClick={() => refetch()}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
            >
              다시 시도
            </button>
          }
        />
      </div>
    )
  }

  return (
    <div className="animate-fade-in flex flex-col gap-4 lg:h-[calc(100dvh-7rem)]">
      {/* PageHeader 축약 — 지도 전용 레이아웃 */}
      <PageHeader
        title="전국 관제 지도"
        subtitle={
          isLoading
            ? '고객사 분포·계약 상태 관제'
            : `표시 ${withCoords.length}곳 / 필터 일치 ${filtered.length}곳 / 전체 ${clients.length}곳${
                // 표시 < 일치 시 차이 사유 명시 — 좌표(지오코딩) 미등록 고객사 안내
                noCoords.length > 0
                  ? ` — 좌표 없는 ${noCoords.length}곳은 지도에 표시되지 않습니다 (고객사 주소를 입력하면 자동 표시)`
                  : ''
              }`
        }
      />

      <div className="flex min-h-0 flex-1 flex-col gap-4 lg:flex-row">
        {/* ── 지도 영역 ──────────────────────────────────────────────── */}
        <section className="relative order-1 min-h-[380px] flex-1 overflow-hidden rounded-3xl border border-hairline bg-graphite lg:order-2 lg:min-h-0">
          {/* key={provider} — 공급자 전환 시 지도 DOM 을 새로 만들어 이전 지도 잔재 제거 */}
          <div key={provider} ref={mapElRef} className="h-full w-full" />

          {/* 지도 공급자 토글 — 키 미설정/오류 상태에서도 전환 가능해야 하므로 오버레이 위(z-20) */}
          <div className="absolute top-4 right-4 z-20 flex overflow-hidden rounded-full border border-hairline bg-graphite/95 text-xs font-medium shadow">
            {PROVIDERS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => switchProvider(p.id)}
                title={
                  keyOf(p.id)
                    ? `${p.label} 지도로 보기`
                    : `${p.label} 지도 — Client ID/키 설정 후 사용 가능`
                }
                className={`px-3 py-1.5 transition-colors ${
                  provider === p.id
                    ? 'bg-primary font-semibold text-on-primary'
                    : 'text-ash hover:bg-elevate hover:text-bone'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          {mapStatus !== 'ready' && (
            <div className="absolute inset-0 flex items-center justify-center bg-graphite/95 p-4">
              {mapStatus === 'loading' && (
                <div className="flex flex-col items-center gap-2 text-slatey">
                  <CircleNotch size={26} className="animate-spin" />
                  <p className="text-sm">지도를 불러오는 중…</p>
                </div>
              )}
              {mapStatus === 'no-key' && (
                <EmptyState
                  icon={<MapTrifold size={36} />}
                  title={
                    provider === 'google'
                      ? 'VITE_GOOGLE_MAPS_KEY 설정 후 지도가 표시됩니다'
                      : '네이버 지도 — Client ID 설정 후 표시됩니다'
                  }
                  description={
                    provider === 'google'
                      ? 'Google Maps API 키를 환경변수(VITE_GOOGLE_MAPS_KEY)로 설정하세요. 키가 없어도 좌측 필터·지역별 집계는 정상 동작합니다.'
                      : 'NCP 콘솔에서 Maps Application 을 등록하고 Client ID 를 환경변수(VITE_NAVER_MAPS_CLIENT_ID)로 설정하세요. 그 전에는 우상단 토글로 구글 지도를 사용할 수 있습니다.'
                  }
                  className="w-full max-w-md"
                />
              )}
              {mapStatus === 'error' && (
                <EmptyState
                  icon={<WarningCircle size={36} />}
                  title="지도를 불러오지 못했습니다"
                  description={
                    provider === 'google'
                      ? '네트워크 또는 API 키 인증 문제일 수 있습니다. 키의 리퍼러 제한 설정을 확인하세요.'
                      : '네트워크 또는 Client ID 인증 문제일 수 있습니다. NCP 콘솔의 서비스 도메인(URL) 등록을 확인하세요.'
                  }
                  className="w-full max-w-md"
                  action={
                    <button
                      type="button"
                      onClick={() => setRetryToken((t) => t + 1)}
                      className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
                    >
                      다시 시도
                    </button>
                  }
                />
              )}
            </div>
          )}

          {/* 범례 오버레이 */}
          {mapStatus === 'ready' && (
            <div className="absolute bottom-4 left-4 flex items-center gap-3 rounded-lg border border-hairline bg-graphite/95 px-3 py-2">
              {STATUS_ORDER.map((s) => (
                <span key={s} className="flex items-center gap-1.5 text-xs text-ash">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full border border-white shadow"
                    style={{ backgroundColor: MARKER_COLORS[s] }}
                  />
                  {STATUS_LABELS[s]}
                </span>
              ))}
            </div>
          )}
        </section>

        {/* ── 좌측 필터·집계 패널 ────────────────────────────────────── */}
        <aside className="order-2 w-full shrink-0 space-y-3 lg:order-1 lg:w-80 lg:overflow-y-auto lg:pr-0.5">
          {/* 필터 */}
          <div className="rounded-3xl border border-hairline bg-graphite p-4">
            <h2 className="text-sm font-bold text-bone">필터링 설정</h2>

            <p className="mt-3 mb-2 text-xs font-semibold text-ash">계약 상태</p>
            <div className="space-y-2">
              {STATUS_ORDER.map((s) => (
                <label
                  key={s}
                  className="flex cursor-pointer items-center gap-2 text-sm text-bone"
                >
                  <input
                    type="checkbox"
                    checked={statusOn[s]}
                    onChange={(e) =>
                      setStatusOn((prev) => ({ ...prev, [s]: e.target.checked }))
                    }
                    className="rounded border-hairline accent-white"
                  />
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: MARKER_COLORS[s] }}
                  />
                  {STATUS_LABELS[s]}
                  <span className="ml-auto text-xs text-slatey">
                    {isLoading ? '—' : `${statusCounts[s]}곳`}
                  </span>
                </label>
              ))}
            </div>

            <p className="mt-4 mb-2 text-xs font-semibold text-ash">최근 활동 기준</p>
            <select
              value={contactFilter}
              onChange={(e) => setContactFilter(e.target.value as ContactFilter)}
              className="h-9 w-full rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
            >
              <option value="">전체 기간</option>
              <option value="WITHIN_30">최근 30일 이내</option>
              <option value="OVER_30">30일 초과 활동 없음</option>
            </select>
          </div>

          {/* 지역별 집계 */}
          <div className="rounded-3xl border border-hairline bg-graphite p-4">
            <h2 className="mb-3 text-sm font-bold text-bone">지역별 현황</h2>
            {isLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-2/3" />
              </div>
            ) : regionAgg.length === 0 ? (
              <p className="py-2 text-center text-xs text-slatey">
                필터 조건에 맞는 고객사가 없습니다
              </p>
            ) : (
              <ul className="space-y-3">
                {regionAgg.map(([region, agg]) => (
                  <li key={region}>
                    {region === '지역 미지정' ? (
                      /* 막다른 정보 방지 — 미지정 항목은 고객사 마스터로 이동해 주소 보완 유도 */
                      <Link
                        to="/clients"
                        title="고객사 마스터에서 주소(지역)를 입력하면 지도·집계에 반영됩니다"
                        className="flex items-center justify-between rounded-md text-sm hover:bg-elevate"
                      >
                        <span className="truncate text-ash underline decoration-dotted underline-offset-2">
                          {region}
                        </span>
                        <span className="ml-2 shrink-0 font-bold text-bone">
                          {agg.total}곳
                        </span>
                      </Link>
                    ) : (
                      <div className="flex items-center justify-between text-sm">
                        <span className="truncate text-ash">{region}</span>
                        <span className="ml-2 shrink-0 font-bold text-bone">
                          {agg.total}곳
                        </span>
                      </div>
                    )}
                    {/* 상태 분포 미니 바 */}
                    <div className="mt-1 flex h-1.5 overflow-hidden rounded-full bg-elevate">
                      {STATUS_ORDER.filter((s) => agg[s] > 0).map((s) => (
                        <span
                          key={s}
                          title={`${STATUS_LABELS[s]} ${agg[s]}곳`}
                          style={{
                            width: `${(agg[s] / agg.total) * 100}%`,
                            backgroundColor: MARKER_COLORS[s],
                          }}
                        />
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* 좌표 미등록 고객사 */}
          {!isLoading && noCoords.length > 0 && (
            <div className="rounded-3xl border border-hairline bg-graphite p-4">
              <h2 className="mb-1 flex items-center gap-1.5 text-sm font-bold text-bone">
                <MapPinLine size={16} className="text-slatey" />
                좌표 미등록 {noCoords.length}곳
              </h2>
              <p className="mb-2 text-xs text-slatey">
                주소 지오코딩(lat/lng) 미등록으로 지도에 표시되지 않는 고객사입니다.
              </p>
              <ul className="max-h-56 space-y-1 overflow-y-auto">
                {noCoords.map((c) => (
                  <li key={c.client_id}>
                    <Link
                      to={`/clients/${c.client_id}`}
                      className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-bone hover:bg-elevate"
                    >
                      <span
                        className="inline-block h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: MARKER_COLORS[c.contract_status] }}
                      />
                      <span className="truncate">{c.company_name}</span>
                      <span className="ml-auto shrink-0 text-xs text-slatey">
                        {c.region ?? '—'}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!isLoading && clients.length === 0 && (
            <EmptyState
              icon={<Buildings size={32} />}
              title="등록된 고객사가 없습니다"
              description="고객사 마스터에서 고객사를 먼저 등록하세요."
            />
          )}
        </aside>
      </div>
    </div>
  )
}
