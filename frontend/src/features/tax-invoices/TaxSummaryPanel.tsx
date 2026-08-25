// 세금계산서 요약(경영전략실) — 기간 KPI(매입·매출·순액·부가세) + 월별 추이 차트.
// 원장(tb_tax_invoice) 파생. 읽기 전용. 자체 SVG 차트(TrendChart) 재사용.
import { useMemo, useState } from 'react'
import { CircleNotch } from '@phosphor-icons/react'
import { TrendChart, type TrendSeries } from '../../components/charts'
import { useTaxInvoiceSummary } from './api'

const won = (v: number) => `${Math.round(v).toLocaleString('ko-KR')}원`
const nfKrw = (v: number) => {
  const a = Math.abs(v)
  if (a >= 1e8) return `${(v / 1e8).toFixed(1)}억`
  if (a >= 1e4) return `${Math.round(v / 1e4).toLocaleString('ko-KR')}만`
  return Math.round(v).toLocaleString('ko-KR')
}

/** 최근 N개월 기본 범위(YYYY-MM-DD) — 로컬 계산(서버 무관) */
function defaultRange(months: number): { date_from: string; date_to: string } {
  const now = new Date()
  const to = now.toISOString().slice(0, 10)
  const from = new Date(now.getFullYear(), now.getMonth() - (months - 1), 1)
    .toISOString()
    .slice(0, 10)
  return { date_from: from, date_to: to }
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: 'up' | 'down' | 'muted' }) {
  const color =
    tone === 'up'
      ? 'text-emerald-600 dark:text-emerald-400'
      : tone === 'down'
        ? 'text-rose-600 dark:text-rose-400'
        : 'text-bone'
  return (
    <div className="rounded-2xl border border-hairline bg-graphite p-4">
      <p className="text-[11px] font-medium uppercase tracking-wider text-slatey">{label}</p>
      <p className={`mt-1 text-xl font-bold tabular-nums ${color}`}>{value}</p>
    </div>
  )
}

const RANGES = [
  { m: 6, label: '6개월' },
  { m: 12, label: '12개월' },
  { m: 24, label: '24개월' },
]

export function TaxSummaryPanel() {
  const [months, setMonths] = useState(12)
  const range = useMemo(() => defaultRange(months), [months])
  const { data, isLoading } = useTaxInvoiceSummary(range)

  const labels = data?.months.map((m) => m.month) ?? []
  const series: TrendSeries[] = data
    ? [
        { key: 'purchase', label: '매입', values: data.months.map((m) => m.purchase), color: '#0ea5e9', kind: 'bar' },
        { key: 'sales', label: '매출', values: data.months.map((m) => m.sales), color: '#10b981', kind: 'bar' },
        { key: 'net', label: '순액', values: data.months.map((m) => m.net), color: '#f59e0b', kind: 'line' },
      ]
    : []

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-bone">
          매입·매출 요약{' '}
          <span className="font-normal text-slatey">· 공급가액(부가세 제외) 기준</span>
        </p>
        <div className="flex rounded-full border border-hairline bg-elevate p-0.5">
          {RANGES.map((r) => (
            <button
              key={r.m}
              type="button"
              onClick={() => setMonths(r.m)}
              className={`rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
                months === r.m ? 'bg-elevate-strong text-bone' : 'text-slatey hover:text-ash'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading && !data ? (
        <p className="flex items-center gap-1.5 py-10 text-sm text-ash">
          <CircleNotch size={15} className="animate-spin" />
          불러오는 중…
        </p>
      ) : !data || (data.sales_count === 0 && data.purchase_count === 0) ? (
        <div className="rounded-2xl border border-dashed border-hairline p-8 text-center text-sm text-slatey">
          이 기간에 적재된 세금계산서가 없습니다. 범위를 넓히거나 원장 탭에서 자료를 반영하세요.
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="매출 공급가액" value={won(data.sales_supply)} tone="up" />
            <Kpi label="매입 공급가액" value={won(data.purchase_supply)} tone="down" />
            <Kpi
              label="순액 (매출−매입)"
              value={won(data.net_supply)}
              tone={data.net_supply >= 0 ? 'up' : 'down'}
            />
            <Kpi label="부가세 (매출/매입)" value={`${nfKrw(data.sales_tax)} / ${nfKrw(data.purchase_tax)}`} tone="muted" />
          </div>

          <div className="rounded-2xl border border-hairline bg-graphite p-4">
            <div className="mb-2 flex items-center gap-3 text-[11px] text-slatey">
              <span className="flex items-center gap-1"><i className="inline-block h-2 w-2 rounded-sm" style={{ background: '#0ea5e9' }} /> 매입</span>
              <span className="flex items-center gap-1"><i className="inline-block h-2 w-2 rounded-sm" style={{ background: '#10b981' }} /> 매출</span>
              <span className="flex items-center gap-1"><i className="inline-block h-2 w-0.5" style={{ background: '#f59e0b', height: 8 }} /> 순액</span>
              <span className="ml-auto">매출 {data.sales_count}건 · 매입 {data.purchase_count}건</span>
            </div>
            {labels.length > 0 ? (
              <TrendChart labels={labels} series={series} formatValue={nfKrw} />
            ) : (
              <p className="py-8 text-center text-xs text-slatey">월별 추이를 그릴 날짜 정보가 없습니다.</p>
            )}
          </div>
        </>
      )}
    </div>
  )
}
