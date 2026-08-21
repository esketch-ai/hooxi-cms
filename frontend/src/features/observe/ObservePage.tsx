// 경영 관찰 대시보드 (/observe) — OBSERVER 전용 읽기전용 경영 요약.
// 신규 백엔드 엔드포인트 없음: OBSERVER 200이 보장된 4개 조회를 조합해 렌더한다.
//   GET /dashboard/stats · GET /projects/stage-delays · GET /finance-ledger · GET /asset-vehicles
// 편집 어포던스 0 — 링크는 읽기 화면(재무 원장·전기버스 자산)으로만. 금액은 SensitiveData money 마스킹.
import { useQuery } from '@tanstack/react-query'
import { Num } from '../../components/Num'
import {
  Buildings,
  Bus,
  ChartLineUp,
  Coins,
  FileText,
  Fire,
  Gauge,
  Package,
  Receipt,
  TrendUp,
  Warehouse,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { ScreenGuide } from '../../components/ScreenGuide'
import { KpiCard } from '../../components/KpiCard'
import { SensitiveData } from '../../components/SensitiveData'
import { SkeletonKpi } from '../../components/Skeleton'
import { api } from '../../lib/api/client'
import { fmtDate, fmtMoney } from '../../lib/format'
import type { DashboardStats } from '../../types'
import { useStageDelays } from '../projects/api'
import { useFinanceLedger } from '../finance-ledger/api'
import { useAssetVehicles } from '../asset-vehicles/api'

/** 감축량 표기 — 소수 2자리·단위 축소(공용 Num 규격, AssetVehiclesPage와 동일 관용구) */
function fmtReduction(value?: number | null) {
  return <Num value={value} unit="tCO₂" />
}

export function ObservePage() {
  // 전사 KPI — 대시보드와 동일 키·fetcher로 캐시 공유
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['dashboard', 'stats'],
    queryFn: async () => {
      const { data } = await api.get<DashboardStats>('/dashboard/stats')
      return data
    },
  })

  // 사업 단계 지연·임박 관찰
  const { data: stageDelays } = useStageDelays()

  // 재무 요약 — 전사 총계만 필요하므로 page_size 최소(totals는 페이지와 무관하게 전체 합)
  const { data: finance, isLoading: financeLoading } = useFinanceLedger({ page: 1, page_size: 1 })
  const totals = finance?.totals

  // 감축량/자산 KPI — 필터 없이 전체 기준
  const { data: assets, isLoading: assetsLoading } = useAssetVehicles({ page: 1, page_size: 1 })
  const avKpi = assets?.kpi

  const kpi = stats?.kpi

  const delayedCount = stageDelays?.delayed.length ?? 0
  const imminentCount = stageDelays?.imminent.length ?? 0
  const stageRows = [
    ...(stageDelays?.delayed ?? []).map((a) => ({ ...a, kind: 'delayed' as const })),
    ...(stageDelays?.imminent ?? []).map((a) => ({ ...a, kind: 'imminent' as const })),
  ].slice(0, 8)

  return (
    <div className="animate-fade-in space-y-5">
      <PageHeader
        title="경영 관찰"
        subtitle={`전사 KPI · 사업 지연 · 재무 · 감축량 요약${stats ? ` (${stats.period})` : ''} — 읽기 전용`}
      />

      <ScreenGuide
        perspective="전사 요약"
        links={[
          { label: '재무 원장', to: '/finance-ledger' },
          { label: '전기버스 자산', to: '/asset-vehicles' },
          { label: '자산관리 보고', to: '/asset-report' },
        ]}
      >
        회사 전체를 한 장으로 보는 <strong className="font-medium text-bone">읽기 전용</strong> 요약입니다.
        지표를 누르면 원본 화면으로 이동합니다. 편집·정산·통지는 각 업무 화면에서 합니다. 재무·예상지급액
        합계는 재무 원장·자산관리 보고와 <strong className="font-medium text-bone">동일 원천의 전사 합</strong>
        입니다.
      </ScreenGuide>

      {/* 운영 현황 — GET /dashboard/stats */}
      <section className="space-y-2">
        <div>
          <h2 className="text-sm font-medium text-bone">운영 현황</h2>
          <p className="mt-0.5 text-xs text-slatey">관리 고객사·보고서·이슈·계약</p>
        </div>
        {statsLoading ? (
          <SkeletonKpi count={4} />
        ) : (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiCard
            title="관리 고객사"
            value={kpi?.total_clients ?? '—'}
            sub={
              kpi != null
                ? `이번 달 신규 ${kpi.client_delta >= 0 ? '+' : ''}${kpi.client_delta}`
                : undefined
            }
            icon={<Buildings size={18} />}
            compact
          />
          <KpiCard
            title="당월 보고서"
            value={
              kpi ? (
                <span>
                  {kpi.report_sent}
                  <span className="text-base font-semibold text-slatey">/{kpi.report_target}</span>
                </span>
              ) : (
                '—'
              )
            }
            sub="발송 완료 / 발송 대상 (취소 제외)"
            icon={<FileText size={18} />}
            compact
          />
          <KpiCard
            title="미처리 긴급 이슈"
            value={kpi?.urgent_open_issues ?? '—'}
            variant="danger"
            icon={<Fire size={18} />}
            compact
          />
          <KpiCard
            title="계약 검토·협의"
            value={kpi?.contract_hold_clients ?? '—'}
            sub="계약 상태 HOLD"
            compact
          />
        </div>
        )}
      </section>

      {/* 재무 (전사 합) — GET /finance-ledger totals(금액 SensitiveData money) */}
      <section className="space-y-2">
        <div>
          <h2 className="text-sm font-medium text-bone">재무 (전사 합)</h2>
          <p className="mt-0.5 text-xs text-slatey">재무 원장과 같은 값</p>
        </div>
        {financeLoading ? (
          <SkeletonKpi count={5} />
        ) : (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <KpiCard
            title="매출인식"
            value={<SensitiveData type="money" value={fmtMoney(totals?.sale_recognized ?? null)} />}
            sub="전사 합"
            icon={<Receipt size={18} />}
            variant="dark"
            to="/finance-ledger"
          />
          <KpiCard
            title="제품(원가)"
            value={<SensitiveData type="money" value={fmtMoney(totals?.product ?? null)} />}
            sub="전사 합"
            icon={<Package size={18} />}
            variant="dark"
            to="/finance-ledger"
          />
          <KpiCard
            title="매출이익"
            value={<SensitiveData type="money" value={fmtMoney(totals?.gross_profit ?? null)} />}
            sub="전사 합"
            icon={<TrendUp size={18} />}
            variant="dark"
            to="/finance-ledger"
          />
          <KpiCard
            title="재고자산"
            value={<SensitiveData type="money" value={fmtMoney(totals?.inventory ?? null)} />}
            sub="전사 합"
            icon={<Warehouse size={18} />}
            variant="dark"
            to="/finance-ledger"
          />
          <KpiCard
            title="재고평가"
            value={<SensitiveData type="money" value={fmtMoney(totals?.inventory_valuation ?? null)} />}
            sub="현재시세 기준"
            icon={<Coins size={18} />}
            variant="dark"
            to="/finance-ledger"
          />
        </div>
        )}
      </section>

      {/* 전기버스 감축·정산 예정 (전사 합) — GET /asset-vehicles kpi(전체 기준) */}
      <section className="space-y-2">
        <div>
          <h2 className="text-sm font-medium text-bone">전기버스 감축·정산 예정 (전사 합)</h2>
          <p className="mt-0.5 text-xs text-slatey">전기버스 자산과 같은 값</p>
        </div>
        {assetsLoading ? (
          <SkeletonKpi count={4} />
        ) : (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiCard
            title="차량 수"
            value={
              avKpi?.vehicle_count != null
                ? `${avKpi.vehicle_count.toLocaleString('ko-KR')}대`
                : '—'
            }
            icon={<Bus size={18} />}
            to="/asset-vehicles"
          />
          <KpiCard
            title="10년 총감축량"
            value={fmtReduction(avKpi?.total_reduction)}
            icon={<ChartLineUp size={18} />}
            to="/asset-vehicles"
          />
          <KpiCard
            title="잔여반영감축량"
            value={fmtReduction(avKpi?.effective_reduction_sum)}
            icon={<Gauge size={18} />}
            to="/asset-vehicles"
          />
          <KpiCard
            title="예상 지급액 합계"
            value={<SensitiveData type="money" value={fmtMoney(avKpi?.expected_payout_sum ?? null)} />}
            icon={<Coins size={18} />}
            variant="dark"
            to="/asset-vehicles"
          />
        </div>
        )}
      </section>

      {/* 사업 단계 지연·임박 — GET /projects/stage-delays (읽기 전용, 편집 진입 없음) */}
      <section className="rounded-3xl border border-hairline bg-graphite p-5">
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-base font-bold text-bone">사업 단계 지연·임박</h2>
          {delayedCount > 0 && (
            <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-xs font-bold text-rose-700 dark:text-rose-300">
              지연 {delayedCount}
            </span>
          )}
          {imminentCount > 0 && (
            <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-bold text-amber-700 dark:text-amber-300">
              임박 {imminentCount}
            </span>
          )}
        </div>
        {stageRows.length === 0 ? (
          <p className="py-6 text-center text-sm text-slatey">지연·임박 사업이 없습니다.</p>
        ) : (
          <ul className="space-y-1.5">
            {stageRows.map((a) => (
              <li
                key={`${a.project_id}-${a.stage_code}`}
                className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm"
              >
                <span
                  className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[11px] font-bold ${
                    a.kind === 'delayed'
                      ? 'bg-rose-500/15 text-rose-700 dark:text-rose-300'
                      : 'bg-amber-500/15 text-amber-700 dark:text-amber-300'
                  }`}
                >
                  {a.kind === 'delayed' ? `지연 ${a.days}일` : `D-${a.days}`}
                </span>
                <span className="truncate font-medium text-bone">{a.project_name}</span>
                <span className="ml-auto shrink-0 text-xs text-slatey">
                  {a.stage_code} · {fmtDate(a.planned_date)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
