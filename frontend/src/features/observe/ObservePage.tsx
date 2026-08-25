// 경영 관찰(Executive View) — OBSERVE_REDESIGN_PLAN OB-R2/R3 전면 재설계.
// 3단계 프로세스: ① 한눈(KPI Δ·추이·퍼널·경고) → ② 클릭 시 개요 드로어(상위 구성+해설,
// 화면 이동 없음 — OBSERVER는 실무 화면 차단) → ③ 개요의 담당자 이름으로 실무자에게 질문.
// 데이터: GET /observe/summary(1콜) + GET /observe/detail(드로어). 읽기 전용.
import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Bus,
  ChartLineUp,
  CircleNotch,
  Coins,
  Fire,
  TreeStructure,
  TrendDown,
  TrendUp,
  Wallet,
  Warning,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { TaxSignalCard } from '../tax-invoices/TaxSignalCard'
import { Drawer } from '../../components/Drawer'
import { Num } from '../../components/Num'
import { SensitiveData } from '../../components/SensitiveData'
import { Skeleton } from '../../components/Skeleton'
import { Donut, MiniBars, TrendChart } from '../../components/charts'
import { api } from '../../lib/api/client'
import { fmtDate } from '../../lib/format'
import { useStageDelays } from '../projects/api'

// ── 응답 타입(백엔드 services/observe.py와 정합) ──
interface KpiEntry {
  value: number | null
  prev?: number
  total12?: number
  rate?: number | null
  avg6?: number | null
  held_qty?: number
  count?: number
  overdue30?: number
}
interface ObserveSummary {
  months: string[]
  kpi: Record<string, KpiEntry>
  finance_trend: { month: string; revenue: number; purchase: number; paid: number }[]
  funnel: { key: string; label: string; count: number; amount: number }[]
  overdue_billed_30: number
  market_rates: { date: string; price: number }[]
  carbon: {
    held_qty: number
    sold_qty: number
    valuation: number | null
    current_rate: number | null
    avg6: number | null
  }
  ev_trend: { month: string; electric: number; total: number; ev_share: number }[]
  project_dist: { status: string; count: number }[]
  report_rate: { month: string; target: number; sent: number; rate: number | null }[]
  urgent_open: number
  activity: { month: string; count: number }[]
}
interface DetailState {
  topic: string
  key?: string
  title: string
}

const PALETTE = {
  revenue: '#10b981', // emerald-500
  purchase: '#64748b', // slate-500
  paid: '#38bdf8', // sky-400
  ev: '#10b981',
  rate: '#a78bfa', // violet-400
}

const fmtWon = (n?: number | null) =>
  n == null ? '—' : `${Math.round(n).toLocaleString('ko-KR')}`

export function ObservePage() {
  const [months, setMonths] = useState<6 | 12 | 24>(12)
  const [detail, setDetail] = useState<DetailState | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['observe', 'summary', months],
    queryFn: async () => (await api.get<ObserveSummary>(`/observe/summary?months=${months}`)).data,
  })
  const { data: stageDelays } = useStageDelays()

  const open = (topic: string, title: string, key?: string) => setDetail({ topic, key, title })

  if (isLoading || !data) {
    return (
      <div className="animate-fade-in space-y-4">
        <PageHeader title="경영 관찰" subtitle="전사 흐름 — 읽기 전용" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-56 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  const k = data.kpi
  const delta = (cur?: number | null, prev?: number | null) =>
    cur == null || prev == null ? null : cur - prev
  const revDelta = delta(k.revenue?.value, k.revenue?.prev)
  const marginDelta = delta(k.margin?.value, k.margin?.prev)
  const latestEv = data.ev_trend[data.ev_trend.length - 1]

  return (
    <div className="animate-fade-in space-y-5">
      <PageHeader
        title="경영 관찰"
        subtitle="회사가 어디로 가고 있나 — 추이·파이프라인·리스크 (요소를 클릭하면 개요와 담당자가 보입니다)"
        actions={
          <div className="flex rounded-full border border-hairline bg-graphite p-0.5">
            {([6, 12, 24] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMonths(m)}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                  months === m ? 'bg-elevate-strong text-bone' : 'text-slatey hover:text-ash'
                }`}
              >
                {m}개월
              </button>
            ))}
          </div>
        }
      />

      {/* ① KPI 스트립 — 전월 대비 Δ. 클릭 → 개요 드로어 */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        <KpiTile
          title="매출인식(당월)"
          masked
          value={<Num value={k.revenue?.value} unit="원" />}
          deltaValue={revDelta}
          sub={
            <>
              기간 누계 <Num value={k.revenue?.total12} unit="원" />
            </>
          }
          onClick={() => open('month', '이번 달 재무 개요')}
        />
        <KpiTile
          title="매출이익(당월)"
          masked
          value={<Num value={k.margin?.value} unit="원" />}
          deltaValue={marginDelta}
          sub="세금계산서 매출−매입 근사"
          onClick={() => open('month', '이번 달 재무 개요')}
        />
        <KpiTile
          title="재고평가"
          masked
          value={<Num value={k.inventory_valuation?.value} unit="원" />}
          sub={
            <>
              보유 <Num value={k.inventory_valuation?.held_qty} unit="tCO₂" /> × 시세{' '}
              {fmtWon(k.inventory_valuation?.rate)}
            </>
          }
          onClick={() => open('inventory', '재고평가 개요')}
        />
        <KpiTile
          title="미수금(청구 후)"
          masked
          danger={(k.receivable?.overdue30 ?? 0) > 0}
          value={<Num value={k.receivable?.value} unit="원" />}
          sub={
            <>
              {k.receivable?.count ?? 0}건
              {(k.receivable?.overdue30 ?? 0) > 0 && (
                <span className="ml-1 font-semibold text-rose-500">
                  · 30일 경과 {k.receivable?.overdue30}건
                </span>
              )}
            </>
          }
          onClick={() => open('receivable', '미수금 개요')}
        />
        <KpiTile
          title="예상 지급액"
          value={<Num value={k.expected_payout?.value} unit="원" />}
          sub="운수사 지급 예정 합"
          onClick={() => open('payout', '예상 지급액 개요')}
        />
        <KpiTile
          title="관리 고객사"
          value={<Num value={k.clients?.value} unit="곳" />}
          sub="계약중 기준"
        />
      </div>

      {/* ② 재무 추이 — 월 클릭 → 그 달 개요 */}
      <section className="rounded-3xl border border-hairline bg-graphite p-5">
        <SectionTitle
          icon={<ChartLineUp size={18} />}
          title={`재무 추이 (${months}개월)`}
          hint="월을 클릭하면 그 달의 개요가 열립니다"
        />
        <TrendChart
          labels={data.months}
          series={[
            {
              key: 'revenue',
              label: '매출(계산서)',
              kind: 'bar',
              color: PALETTE.revenue,
              values: data.finance_trend.map((r) => r.revenue),
            },
            {
              key: 'purchase',
              label: '매입(계산서)',
              kind: 'bar',
              color: PALETTE.purchase,
              values: data.finance_trend.map((r) => r.purchase),
            },
            {
              key: 'paid',
              label: '정산 입금',
              kind: 'line',
              color: PALETTE.paid,
              values: data.finance_trend.map((r) => r.paid),
            },
          ]}
          onSelect={(m) => open('month', `${m} 재무 개요`, m)}
        />
      </section>

      {/* ③ 정산 파이프라인 + ④ 탄소배출권 */}
      <div className="grid gap-4 xl:grid-cols-2">
        <section className="rounded-3xl border border-hairline bg-graphite p-5">
          <SectionTitle
            icon={<Wallet size={18} />}
            title="정산 파이프라인"
            hint="단계 클릭 → 건 목록·담당자"
            badge={
              data.overdue_billed_30 > 0 ? (
                <span className="flex items-center gap-1 rounded-full bg-rose-500/15 px-2 py-0.5 text-[11px] font-bold text-rose-600 dark:text-rose-300">
                  <Warning size={12} weight="fill" />
                  청구 30일 경과 {data.overdue_billed_30}건
                </span>
              ) : undefined
            }
          />
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {data.funnel.map((f, i) => (
              <button
                key={f.key}
                type="button"
                onClick={() => open('funnel', `정산 ${f.label} 개요`, f.key)}
                className="rounded-2xl border border-hairline bg-elevate p-3 text-left hover:bg-elevate-strong"
              >
                <p className="text-xs text-slatey">
                  {i + 1}. {f.label}
                </p>
                <p className="mt-1 font-mono text-xl font-bold tabular-nums text-bone">{f.count}</p>
                <div className="mt-0.5 truncate text-[11px] text-slatey">
                  <SensitiveData type="money" value={<Num value={f.amount} unit="원" />} />
                </div>
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-3xl border border-hairline bg-graphite p-5">
          <SectionTitle icon={<Coins size={18} />} title="탄소배출권" hint="시세·보유 클릭 가능" />
          <div className="flex flex-wrap items-center gap-5">
            <Donut
              slices={[
                { key: 'held', label: '보유', value: data.carbon.held_qty, color: PALETTE.ev },
                { key: 'sold', label: '매각', value: data.carbon.sold_qty, color: PALETTE.purchase },
              ]}
              onSelect={() => open('inventory', '재고평가 개요')}
            />
            <div className="min-w-0 flex-1">
              <button
                type="button"
                onClick={() => open('rate', '시세 등록 이력')}
                className="block w-full text-left"
              >
                {data.market_rates.length >= 2 ? (
                  <TrendChart
                    labels={data.market_rates.map((r) => r.date.slice(2, 7))}
                    series={[
                      {
                        key: 'rate',
                        label: '시세(원/tCO₂)',
                        kind: 'line',
                        color: PALETTE.rate,
                        values: data.market_rates.map((r) => r.price),
                      },
                    ]}
                    height={120}
                  />
                ) : (
                  <p className="text-xs text-slatey">
                    시세 이력이 2건 이상 쌓이면 추이가 표시됩니다.
                  </p>
                )}
              </button>
              <p className="mt-1 text-[11px] text-slatey">
                현재 {fmtWon(data.carbon.current_rate)}원 · 6개월 평균 {fmtWon(data.carbon.avg6)}원
              </p>
            </div>
          </div>
        </section>
      </div>

      {/* ⑤ 전기 전환 + ⑥ 사업 분포 */}
      <div className="grid gap-4 xl:grid-cols-2">
        <section className="rounded-3xl border border-hairline bg-graphite p-5">
          <SectionTitle icon={<Bus size={18} />} title="전기버스 전환 추이" hint="월 클릭 → 지역별 표" />
          {data.ev_trend.length ? (
            <>
              <TrendChart
                labels={data.ev_trend.map((r) => r.month)}
                series={[
                  {
                    key: 'ev',
                    label: '전기 비중(%)',
                    kind: 'line',
                    color: PALETTE.ev,
                    values: data.ev_trend.map((r) => r.ev_share),
                  },
                ]}
                height={130}
                onSelect={(m) => open('ev', `${m} 지역별 전환 현황`, m)}
                formatValue={(n) => `${n}%`}
              />
              {latestEv && (
                <p className="mt-1 text-[11px] text-slatey">
                  최신 {latestEv.month}: 전기 {latestEv.electric.toLocaleString()}대 /{' '}
                  {latestEv.total.toLocaleString()}대 ({latestEv.ev_share}%)
                </p>
              )}
            </>
          ) : (
            <p className="text-xs text-slatey">계약대수 현황이 업로드되면 전환 추이가 표시됩니다.</p>
          )}
        </section>

        <section className="rounded-3xl border border-hairline bg-graphite p-5">
          <SectionTitle
            icon={<TreeStructure size={18} />}
            title="감축 사업 분포"
            hint="상태 클릭 → 사업 목록"
          />
          <Donut
            slices={data.project_dist.map((d, i) => ({
              key: d.status,
              label: d.status,
              value: d.count,
              color: ['#10b981', '#38bdf8', '#a78bfa', '#f59e0b', '#64748b', '#f43f5e'][i % 6],
            }))}
            onSelect={(status) => open('project', `'${status}' 사업 목록`, status)}
          />
        </section>
      </div>

      {/* 사업 단계 지연·임박(기존 위젯 유지) */}
      {stageDelays && (stageDelays.delayed.length > 0 || stageDelays.imminent.length > 0) && (
        <section className="rounded-3xl border border-hairline bg-graphite p-5">
          <SectionTitle icon={<Fire size={18} />} title="사업 단계 지연·임박" />
          <ul className="space-y-1.5">
            {[
              ...stageDelays.delayed.map((a) => ({ ...a, kind: 'delayed' as const })),
              ...stageDelays.imminent.map((a) => ({ ...a, kind: 'imminent' as const })),
            ]
              .slice(0, 8)
              .map((a) => (
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
        </section>
      )}

      {/* ⑦ 운영 신호 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <section className="rounded-3xl border border-hairline bg-graphite p-4">
          <p className="mb-2 text-xs font-medium text-ash">보고서 발송률(월별)</p>
          <MiniBars
            items={data.report_rate
              .filter((r) => r.target > 0)
              .slice(-6)
              .map((r) => ({
                key: r.month,
                label: r.month,
                value: r.rate ?? 0,
                sub: `${r.sent}/${r.target}`,
              }))}
            valueLabel={(v) => `${v}%`}
          />
        </section>
        <section className="rounded-3xl border border-hairline bg-graphite p-4">
          <p className="mb-2 text-xs font-medium text-ash">미처리 긴급 이슈</p>
          <button
            type="button"
            onClick={() => open('signal', '미처리 긴급 이슈', 'urgent')}
            className="block text-left"
          >
            <span
              className={`font-mono text-3xl font-bold tabular-nums ${
                data.urgent_open > 0 ? 'text-rose-500' : 'text-bone'
              }`}
            >
              {data.urgent_open}
            </span>
            <span className="ml-1 text-xs text-slatey">건 — 클릭하면 목록·담당자</span>
          </button>
        </section>
        <section className="rounded-3xl border border-hairline bg-graphite p-4">
          <p className="mb-2 text-xs font-medium text-ash">월별 활동량</p>
          <MiniBars
            items={data.activity.slice(-6).map((a) => ({
              key: a.month,
              label: a.month,
              value: a.count,
            }))}
            onSelect={(m) => open('signal', `${m} 활동 기록`, `activity:${m}`)}
          />
        </section>
        <TaxSignalCard />
      </div>

      {/* 개요 드로어 — 3단계 프로세스의 2단계 */}
      <DetailDrawer detail={detail} onClose={() => setDetail(null)} />
    </div>
  )
}

// ── 보조 컴포넌트 ──────────────────────────────────────────────────
function SectionTitle({
  icon,
  title,
  hint,
  badge,
}: {
  icon: ReactNode
  title: string
  hint?: string
  badge?: ReactNode
}) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <span className="text-bone">{icon}</span>
      <h2 className="text-sm font-bold text-bone">{title}</h2>
      {badge}
      {hint && <span className="ml-auto text-[11px] text-slatey">{hint}</span>}
    </div>
  )
}

function KpiTile({
  title,
  value,
  sub,
  deltaValue,
  masked = false,
  danger = false,
  onClick,
}: {
  title: string
  value: ReactNode
  sub?: ReactNode
  deltaValue?: number | null
  masked?: boolean
  danger?: boolean
  onClick?: () => void
}) {
  const body = (
    <>
      <p className="flex items-center gap-1 text-xs font-medium text-ash">{title}</p>
      <div
        className={`mt-1.5 min-w-0 break-words text-lg font-bold tracking-tight ${
          danger ? 'text-rose-600 dark:text-rose-300' : 'text-bone'
        }`}
      >
        {masked ? <SensitiveData type="money" value={value} /> : value}
      </div>
      <div className="mt-0.5 flex items-center gap-1 text-[11px] text-slatey">
        {deltaValue != null && deltaValue !== 0 && (
          <span
            className={`flex items-center gap-0.5 font-semibold ${
              deltaValue > 0
                ? 'text-emerald-600 dark:text-emerald-400'
                : 'text-rose-600 dark:text-rose-400'
            }`}
          >
            {deltaValue > 0 ? <TrendUp size={11} /> : <TrendDown size={11} />}
            <Num value={Math.abs(deltaValue)} />
          </span>
        )}
        {sub && <span className="min-w-0 truncate">{sub}</span>}
      </div>
    </>
  )
  if (!onClick) {
    return <div className="rounded-2xl border border-hairline bg-graphite p-3.5">{body}</div>
  }
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-2xl border border-hairline bg-graphite p-3.5 text-left transition-colors hover:bg-elevate"
      title="클릭하면 개요가 열립니다"
    >
      {body}
    </button>
  )
}

// ── 개요 드로어 — topic별 데이터 렌더(담당자 이름 포함) ──
interface DetailResponse {
  topic: string
  key?: string | null
  explain: string
  total?: number
  sales_total?: number
  purchase_total?: number
  current_rate?: number | null
  items?: Record<string, unknown>[]
  sales_top?: Record<string, unknown>[]
  purchase_top?: Record<string, unknown>[]
  paid?: Record<string, unknown>[]
}

type Col = { k: string; label: string; kind?: 'money' | 'num' | 'text' }
const MGR: Col = { k: 'manager', label: '담당자' }

function DetailDrawer({ detail, onClose }: { detail: DetailState | null; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['observe', 'detail', detail?.topic, detail?.key],
    enabled: !!detail,
    queryFn: async () => {
      const params = new URLSearchParams({ topic: detail!.topic })
      if (detail!.key) params.set('key', detail!.key)
      return (await api.get<DetailResponse>(`/observe/detail?${params}`)).data
    },
  })

  const renderRows = (rows: Record<string, unknown>[] | undefined, cols: Col[]) => {
    if (!rows || rows.length === 0) {
      return (
        <p className="rounded-lg border border-dashed border-hairline px-3 py-4 text-center text-xs text-slatey">
          해당 내역이 없습니다.
        </p>
      )
    }
    return (
      <div className="overflow-x-auto rounded-xl border border-hairline">
        <table className="w-full text-left text-xs">
          <thead className="bg-elevate text-slatey">
            <tr>
              {cols.map((c) => (
                <th
                  key={c.k}
                  className={`px-2.5 py-1.5 font-medium ${
                    c.kind && c.kind !== 'text' ? 'text-right' : ''
                  }`}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {rows.map((r, i) => (
              <tr key={i}>
                {cols.map((c) => {
                  const v = r[c.k]
                  if (c.kind === 'money' || c.kind === 'num') {
                    return (
                      <td
                        key={c.k}
                        className="px-2.5 py-1.5 text-right font-mono tabular-nums text-bone"
                      >
                        {typeof v === 'number' ? (
                          <Num value={v} unit={c.kind === 'money' ? '원' : undefined} />
                        ) : (
                          '—'
                        )}
                      </td>
                    )
                  }
                  return (
                    <td key={c.k} className="max-w-[160px] truncate px-2.5 py-1.5 text-ash">
                      {v == null || v === '' ? '—' : String(v)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <Drawer open={!!detail} onClose={onClose} title={detail?.title} size="lg">
      {isLoading || !data ? (
        <p className="flex items-center gap-1.5 text-sm text-ash">
          <CircleNotch size={15} className="animate-spin" />
          개요를 불러오는 중…
        </p>
      ) : (
        <div className="space-y-4 text-sm">
          <p className="rounded-xl border border-hairline bg-elevate px-3.5 py-2.5 text-xs leading-relaxed text-ash">
            {data.explain}
            <span className="mt-1 block text-[11px] text-slatey">
              더 자세한 내용은 각 행의 <b className="text-bone">담당자</b>에게 문의하세요.
            </span>
          </p>

          {data.topic === 'month' && (
            <>
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-xl border border-hairline bg-elevate p-3">
                  <p className="text-[11px] text-slatey">매출 합계</p>
                  <SensitiveData type="money" value={<Num value={data.sales_total} unit="원" />} />
                </div>
                <div className="rounded-xl border border-hairline bg-elevate p-3">
                  <p className="text-[11px] text-slatey">매입 합계</p>
                  <SensitiveData
                    type="money"
                    value={<Num value={data.purchase_total} unit="원" />}
                  />
                </div>
              </div>
              <p className="text-xs font-medium text-ash">매출 상위</p>
              {renderRows(data.sales_top, [
                { k: 'counterpart', label: '상대처' },
                { k: 'amount', label: '공급가액', kind: 'money' },
                { k: 'project_name', label: '사업' },
                MGR,
              ])}
              <p className="text-xs font-medium text-ash">매입 상위</p>
              {renderRows(data.purchase_top, [
                { k: 'counterpart', label: '상대처' },
                { k: 'amount', label: '공급가액', kind: 'money' },
                { k: 'project_name', label: '사업' },
                MGR,
              ])}
              <p className="text-xs font-medium text-ash">정산 입금</p>
              {renderRows(data.paid, [
                { k: 'client_name', label: '운수사' },
                { k: 'amount', label: '입금액', kind: 'money' },
                { k: 'completed_at', label: '입금일' },
                MGR,
              ])}
            </>
          )}

          {data.topic === 'receivable' &&
            renderRows(data.items, [
              { k: 'client_name', label: '운수사' },
              { k: 'project_name', label: '사업' },
              { k: 'amount', label: '확정액', kind: 'money' },
              { k: 'days', label: '경과일', kind: 'num' },
              MGR,
            ])}

          {data.topic === 'funnel' &&
            renderRows(data.items, [
              { k: 'client_name', label: '운수사' },
              { k: 'project_name', label: '사업' },
              { k: 'amount', label: '금액', kind: 'money' },
              { k: 'at', label: '기준일' },
              MGR,
            ])}

          {data.topic === 'rate' &&
            renderRows(data.items, [
              { k: 'date', label: '유효일' },
              { k: 'price', label: '단가', kind: 'money' },
              { k: 'note', label: '비고' },
              { k: 'manager', label: '등록자' },
            ])}

          {data.topic === 'inventory' &&
            renderRows(data.items, [
              { k: 'project_name', label: '사업' },
              { k: 'held_qty', label: '보유(tCO₂)', kind: 'num' },
              { k: 'valuation', label: '평가액', kind: 'money' },
              MGR,
            ])}

          {data.topic === 'payout' &&
            renderRows(data.items, [
              { k: 'client_name', label: '운수사' },
              { k: 'amount', label: '예상지급액', kind: 'money' },
              MGR,
            ])}

          {data.topic === 'ev' &&
            renderRows(data.items, [
              { k: 'region', label: '지역' },
              { k: 'license', label: '면허', kind: 'num' },
              { k: 'electric', label: '전기', kind: 'num' },
              { k: 'share', label: '비중(%)', kind: 'num' },
            ])}

          {data.topic === 'project' &&
            renderRows(data.items, [
              { k: 'project_name', label: '사업' },
              { k: 'status', label: '상태' },
              { k: 'vehicle_count', label: '차량', kind: 'num' },
              { k: 'manager', label: '담당 PM' },
            ])}

          {data.topic === 'signal' &&
            renderRows(data.items, [
              { k: 'title', label: '제목' },
              { k: 'client_name', label: '고객사' },
              { k: 'at', label: '일자' },
              MGR,
            ])}
        </div>
      )}
    </Drawer>
  )
}
