// 운수사 참여 현황(라이프사이클 보) — 전 운수사 크로스 집계: 참여율·상태별 대수·3단계·오차 신호.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CircleNotch } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { useCodes } from '../../lib/api/queries'
import { useParticipationOverview } from './api'

const tco2 = (v?: number | null) => (v == null ? '—' : `${v.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}`)

function RatePill({ v }: { v?: number | null }) {
  if (v == null) return <span className="text-slatey">—</span>
  const tone = v >= 100 ? 'text-emerald-600 dark:text-emerald-400' : v >= 80 ? 'text-ash' : 'text-amber-600 dark:text-amber-400'
  return <span className={tone}>{v.toFixed(0)}%</span>
}

function Tile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: boolean }) {
  return (
    <div className="rounded-2xl border border-hairline bg-graphite p-4">
      <p className="text-[11px] font-medium uppercase tracking-wider text-slatey">{label}</p>
      <p className={`mt-1 text-xl font-bold tabular-nums ${tone ? 'text-emerald-600 dark:text-emerald-400' : 'text-bone'}`}>{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-slatey">{sub}</p>}
    </div>
  )
}

export function OperatorParticipationPage() {
  const [region, setRegion] = useState('')
  const { options: regionOptions } = useCodes('REGION')
  const { data, isLoading } = useParticipationOverview(region || undefined)
  const rows = data?.items ?? []

  return (
    <div className="animate-fade-in space-y-5">
      <PageHeader
        title="운수사 참여 현황"
        subtitle="전 운수사 크로스 집계 — 참여율·상태별 대수·3단계 감축량·달성/확정 오차를 한눈에"
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile label="전체 참여율" value={data?.participation_rate != null ? `${data.participation_rate}%` : '—'}
          sub={data ? `참여 ${data.total_participating} / 보유 ${data.total_owned} · 운수사 ${data.operator_count}` : ''} tone />
        <Tile label="예상 감축량(합계)" value={`${tco2(data?.expected_total)} tCO₂`} />
        <Tile label="모니터링(합계)" value={`${tco2(data?.monitoring_total)} tCO₂`}
          sub={data && data.expected_total ? `달성 ${Math.round((data.monitoring_total / data.expected_total) * 100)}%` : ''} />
        <Tile label="최종 확정(합계)" value={`${tco2(data?.final_total)} tCO₂`}
          sub={data && data.expected_total ? `확정 ${Math.round((data.final_total / data.expected_total) * 100)}%` : ''} tone />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={region}
          onChange={(e) => setRegion(e.target.value)}
          className="h-9 rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone focus:border-white/30 focus:outline-none"
        >
          <option value="">전체 권역</option>
          {regionOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <span className="text-xs text-slatey">참여율 높은 순 · 운수사명을 누르면 감축 참여 상세로 이동</span>
      </div>

      <section className="rounded-2xl border border-hairline bg-graphite p-5">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="border-b border-hairline text-[11px] uppercase tracking-wider text-slatey">
              <tr>
                <th className="px-2 py-2">운수사</th>
                <th className="px-2 py-2">권역</th>
                <th className="px-2 py-2 text-right">보유</th>
                <th className="px-2 py-2 text-right">참여</th>
                <th className="px-2 py-2 text-right">기·현·미</th>
                <th className="px-2 py-2 text-right">참여율</th>
                <th className="px-2 py-2 text-right">예상</th>
                <th className="px-2 py-2 text-right">모니터링</th>
                <th className="px-2 py-2 text-right">달성률</th>
                <th className="px-2 py-2 text-right">최종</th>
                <th className="px-2 py-2 text-right">확정률</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && !data ? (
                <tr><td colSpan={11} className="px-2 py-8 text-center text-ash"><CircleNotch size={16} className="mx-auto animate-spin" /></td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={11} className="px-2 py-8 text-center text-slatey">집계할 운수사 데이터가 없습니다.</td></tr>
              ) : (
                rows.map((r) => (
                  <tr key={r.client_id} className="border-b border-hairline/60">
                    <td className="px-2 py-2 font-medium">
                      <Link to={`/clients/${r.client_id}`} className="text-bone hover:underline">{r.operator_name ?? '—'}</Link>
                    </td>
                    <td className="px-2 py-2 text-ash">{r.region ?? '—'}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-ash">{r.owned_count}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-bone">{r.participating_count}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-slatey">{r.completed_count}·{r.ongoing_count}·{r.not_participated_count}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{r.participation_rate != null ? <span className={r.participation_rate >= 80 ? 'text-emerald-600 dark:text-emerald-400' : r.participation_rate >= 40 ? 'text-ash' : 'text-amber-600 dark:text-amber-400'}>{r.participation_rate}%</span> : '—'}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-ash">{tco2(r.expected_reduction)}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-sky-600 dark:text-sky-400">{r.monitoring_reduction ? tco2(r.monitoring_reduction) : '—'}</td>
                    <td className="px-2 py-2 text-right tabular-nums"><RatePill v={r.ach_monitoring} /></td>
                    <td className="px-2 py-2 text-right tabular-nums text-bone">{r.final_reduction ? tco2(r.final_reduction) : '—'}</td>
                    <td className="px-2 py-2 text-right tabular-nums"><RatePill v={r.ach_final} /></td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
