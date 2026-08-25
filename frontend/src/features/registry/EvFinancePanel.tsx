// 전기버스 도입 재무(민간투자비율 근거) — 차량가액·보조금·자부담금·민간비율(D2).
import { useState } from 'react'
import { CircleNotch, UploadSimple } from '@phosphor-icons/react'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import { useEvFinance, useEvFinanceSummary, useImportEvFinance } from './financeApi'

const won = (v?: number | null) => (v == null ? '—' : `${Math.round(v).toLocaleString('ko-KR')}원`)
const eok = (v?: number | null) => (v == null ? '—' : `${(v / 1e8).toFixed(1)}억`)
const pct = (v?: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)

export function EvFinancePanel() {
  const { showToast } = useToast()
  const { user } = useAuth()
  const canWrite = !!user && ['ADMIN', 'MANAGER', 'STAFF'].includes(user.role)
  const { data: summary } = useEvFinanceSummary()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 50
  const { data, isLoading } = useEvFinance({ search: search.trim() || undefined, page, page_size: pageSize })
  const importM = useImportEvFinance()

  const onUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    try {
      const r = await importM.mutateAsync(files[0])
      showToast(`적재 완료 — ${r.created}대 · 운수사매칭 ${r.client_matched}`, 'success')
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '적재에 실패했습니다.', 'danger')
    }
  }

  const total = data?.total ?? 0
  const maxPage = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="space-y-4">
      {/* 요약 */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile label="대수" value={(summary?.count ?? 0).toLocaleString('ko-KR')} />
        <Tile label="차량가액 총액" value={eok(summary?.vehicle_value_total)} />
        <Tile label="보조금 총액" value={eok(summary?.subsidy_total)} />
        <Tile label="평균 민간비율" value={pct(summary?.avg_private_ratio)} tone />
      </div>
      <p className="text-xs text-slatey">
        민간비율 = 자부담금 ÷ 차량가액(출고가+취득세+농특세). 자부담금 = 출고가 − 보조금(저상+전기차).
        엑셀 산정값을 그대로 보관(감사 근거).
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          placeholder="차량번호·운수사 검색"
          className="h-9 w-56 rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
        />
        {canWrite && (
          <label className="ml-auto flex cursor-pointer items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate">
            {importM.isPending ? <CircleNotch size={15} className="animate-spin" /> : <UploadSimple size={15} />}
            차량가액·보조금 엑셀 적재
            <input type="file" accept=".xlsx" className="hidden" onChange={(e) => onUpload(e.target.files)} />
          </label>
        )}
      </div>

      <section className="rounded-2xl border border-hairline bg-graphite p-5">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="border-b border-hairline text-[11px] uppercase tracking-wider text-slatey">
              <tr>
                <th className="px-2 py-2">차량번호</th>
                <th className="px-2 py-2">운수사</th>
                <th className="px-2 py-2 text-right">출고가</th>
                <th className="px-2 py-2 text-right">차량가액</th>
                <th className="px-2 py-2 text-right">보조금</th>
                <th className="px-2 py-2 text-right">자부담금</th>
                <th className="px-2 py-2 text-right">민간비율</th>
                <th className="px-2 py-2">권역</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && !data ? (
                <tr><td colSpan={8} className="px-2 py-8 text-center text-ash"><CircleNotch size={16} className="mx-auto animate-spin" /></td></tr>
              ) : (data?.items ?? []).length === 0 ? (
                <tr><td colSpan={8} className="px-2 py-8 text-center text-slatey">데이터가 없습니다. {canWrite ? '엑셀을 적재하세요.' : ''}</td></tr>
              ) : (
                (data?.items ?? []).map((r) => (
                  <tr key={r.ev_finance_id} className="border-b border-hairline/60">
                    <td className="px-2 py-2 font-medium text-bone">{r.vehicle_no}</td>
                    <td className="px-2 py-2 text-ash">{r.client_name ?? r.operator_name ?? '—'}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-ash">{won(r.release_price)}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-bone">{won(r.vehicle_value)}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-sky-600 dark:text-sky-400">{won((r.low_floor_subsidy ?? 0) + (r.ev_subsidy ?? 0))}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-ash">{won(r.self_payment)}</td>
                    <td className="px-2 py-2 text-right tabular-nums font-semibold text-emerald-600 dark:text-emerald-400">{pct(r.private_ratio)}</td>
                    <td className="px-2 py-2 text-ash">{r.region ?? '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {maxPage > 1 && (
          <div className="mt-3 flex items-center justify-end gap-2 text-sm">
            <button type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))} className="rounded-lg border border-hairline px-3 py-1.5 text-bone hover:bg-elevate disabled:opacity-40">이전</button>
            <span className="text-ash">{page} / {maxPage}</span>
            <button type="button" disabled={page >= maxPage} onClick={() => setPage((p) => Math.min(maxPage, p + 1))} className="rounded-lg border border-hairline px-3 py-1.5 text-bone hover:bg-elevate disabled:opacity-40">다음</button>
          </div>
        )}
      </section>
    </div>
  )
}

function Tile({ label, value, tone }: { label: string; value: string; tone?: boolean }) {
  return (
    <div className="rounded-2xl border border-hairline bg-graphite p-4">
      <p className="text-[11px] font-medium uppercase tracking-wider text-slatey">{label}</p>
      <p className={`mt-1 text-2xl font-bold tabular-nums ${tone ? 'text-emerald-600 dark:text-emerald-400' : 'text-bone'}`}>{value}</p>
    </div>
  )
}
