// 세금계산서 축별 집계(경영전략실) — 거래처별/사업별/자사법인별 매입·매출·순액.
// 원장 파생·읽기 전용. 기간 토글 + 엑셀 내보내기(현재 기간).
import { useMemo, useState } from 'react'
import { CircleNotch, DownloadSimple } from '@phosphor-icons/react'
import { useToast } from '../../components/Toast'
import { downloadExport } from '../../lib/export'
import { useTaxInvoiceBreakdown } from './api'

const nfKrw = (v: number) => {
  const a = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (a >= 1e8) return `${sign}${(a / 1e8).toFixed(1)}억`
  if (a >= 1e4) return `${sign}${Math.round(a / 1e4).toLocaleString('ko-KR')}만`
  return `${sign}${Math.round(a).toLocaleString('ko-KR')}`
}

function defaultRange(months: number): { date_from: string; date_to: string } {
  const now = new Date()
  const to = now.toISOString().slice(0, 10)
  const from = new Date(now.getFullYear(), now.getMonth() - (months - 1), 1)
    .toISOString()
    .slice(0, 10)
  return { date_from: from, date_to: to }
}

const AXES = [
  { key: 'counterpart', label: '거래처별' },
  { key: 'project', label: '사업별' },
  { key: 'entity', label: '자사법인별' },
]
const RANGES = [
  { m: 6, label: '6개월' },
  { m: 12, label: '12개월' },
  { m: 24, label: '24개월' },
]

export function TaxBreakdownPanel() {
  const { showToast } = useToast()
  const [axis, setAxis] = useState('counterpart')
  const [months, setMonths] = useState(12)
  const [exporting, setExporting] = useState(false)
  const range = useMemo(() => defaultRange(months), [months])
  const { data, isLoading } = useTaxInvoiceBreakdown(axis, range)

  const onExport = async () => {
    if (exporting) return
    setExporting(true)
    try {
      await downloadExport(
        '/tax-invoices/export',
        { date_from: range.date_from, date_to: range.date_to },
        '세금계산서.xlsx',
      )
      showToast('엑셀 내보내기를 시작했습니다.', 'success')
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '내보내기에 실패했습니다.', 'danger')
    } finally {
      setExporting(false)
    }
  }

  const rows = data?.rows ?? []

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1 rounded-full border border-hairline bg-elevate p-0.5">
          {AXES.map((a) => (
            <button
              key={a.key}
              type="button"
              onClick={() => setAxis(a.key)}
              className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition-colors ${
                axis === a.key ? 'bg-elevate-strong text-bone' : 'text-slatey hover:text-ash'
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
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
          <button
            type="button"
            onClick={onExport}
            disabled={exporting}
            className="flex items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-xs font-medium text-bone hover:bg-elevate disabled:opacity-50"
          >
            <DownloadSimple size={14} />
            {exporting ? '내보내는 중…' : '엑셀 내보내기'}
          </button>
        </div>
      </div>

      <section className="rounded-2xl border border-hairline bg-graphite p-5">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-hairline text-[11px] uppercase tracking-wider text-slatey">
              <tr>
                <th className="px-2 py-2">{AXES.find((a) => a.key === axis)?.label.replace('별', '')}</th>
                <th className="px-2 py-2 text-right">매출</th>
                <th className="px-2 py-2 text-right">매입</th>
                <th className="px-2 py-2 text-right">순액</th>
                <th className="px-2 py-2 text-right">건수</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && !data ? (
                <tr>
                  <td colSpan={5} className="px-2 py-8 text-center text-ash">
                    <CircleNotch size={16} className="mx-auto animate-spin" />
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-2 py-8 text-center text-slatey">
                    이 기간에 집계할 세금계산서가 없습니다.
                  </td>
                </tr>
              ) : (
                rows.map((r) => (
                  <tr key={r.key} className="border-b border-hairline/60">
                    <td className="max-w-[220px] truncate px-2 py-2 text-bone" title={r.label}>
                      {r.label}
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums text-emerald-600 dark:text-emerald-400">
                      {nfKrw(r.sales)}
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums text-sky-600 dark:text-sky-400">
                      {nfKrw(r.purchase)}
                    </td>
                    <td
                      className={`px-2 py-2 text-right font-semibold tabular-nums ${
                        r.net >= 0 ? 'text-bone' : 'text-rose-600 dark:text-rose-400'
                      }`}
                    >
                      {nfKrw(r.net)}
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums text-ash">{r.count}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {rows.length >= 100 && (
          <p className="mt-2 text-[11px] text-slatey">상위 100건만 표시됩니다 — 세부는 엑셀 내보내기로.</p>
        )}
      </section>
    </div>
  )
}
