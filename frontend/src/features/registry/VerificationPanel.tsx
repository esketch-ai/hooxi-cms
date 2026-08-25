// 대체도입 자동 검증(D4) — 베이스라인↔전기버스 페어링 룰 검증. 수작업 대사 대체.
import { useState } from 'react'
import { CheckCircle, WarningCircle } from '@phosphor-icons/react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api/client'

interface VItem {
  vehicle_no?: string | null
  operator_name?: string | null
  client_name?: string | null
  region?: string | null
  old_vin?: string | null
  new_vin?: string | null
  old_fuel?: string | null
  status: string
  reasons: string[]
}
interface VResp { total: number; passed: number; failed: number; items: VItem[] }

export function VerificationPanel() {
  const [onlyFailed, setOnlyFailed] = useState(false)
  const { data, isLoading } = useQuery({
    queryKey: ['registry', 'verification', onlyFailed],
    queryFn: async () =>
      (await api.get<VResp>('/reduction-registry/verification', { params: { only_failed: onlyFailed } })).data,
  })
  const passRate = data && data.total > 0 ? Math.round((data.passed / data.total) * 100) : 0

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-2xl border border-hairline bg-graphite p-4">
          <p className="text-[11px] font-medium uppercase tracking-wider text-slatey">검증 대상(대체도입)</p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-bone">{data?.total ?? 0}</p>
        </div>
        <div className="rounded-2xl border border-hairline bg-graphite p-4">
          <p className="text-[11px] font-medium uppercase tracking-wider text-slatey">통과</p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-emerald-600 dark:text-emerald-400">{data?.passed ?? 0} <span className="text-sm text-slatey">({passRate}%)</span></p>
        </div>
        <div className="rounded-2xl border border-hairline bg-graphite p-4">
          <p className="text-[11px] font-medium uppercase tracking-wider text-slatey">실패</p>
          <p className={`mt-1 text-2xl font-bold tabular-nums ${(data?.failed ?? 0) > 0 ? 'text-rose-500' : 'text-bone'}`}>{data?.failed ?? 0}</p>
        </div>
      </div>
      <p className="text-xs text-slatey">규칙: ①베이스라인 존재 ②VIN 상이(old≠new) ③기존 연료 경유/CNG ④신규 전기. (폐차일 ≤ 도입일은 폐차증명 문서 기반 — 추후)</p>

      <label className="flex w-fit cursor-pointer items-center gap-2 text-sm text-bone">
        <input type="checkbox" checked={onlyFailed} onChange={(e) => setOnlyFailed(e.target.checked)} />
        실패 건만 보기
      </label>

      <section className="rounded-2xl border border-hairline bg-graphite p-5">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-left text-sm">
            <thead className="border-b border-hairline text-[11px] uppercase tracking-wider text-slatey">
              <tr>
                <th className="px-2 py-2">검증</th>
                <th className="px-2 py-2">차량번호</th>
                <th className="px-2 py-2">운수사</th>
                <th className="px-2 py-2">기존VIN → 신규VIN</th>
                <th className="px-2 py-2">기존연료</th>
                <th className="px-2 py-2">사유</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={6} className="px-2 py-8 text-center text-ash">불러오는 중…</td></tr>
              ) : (data?.items ?? []).length === 0 ? (
                <tr><td colSpan={6} className="px-2 py-8 text-center text-slatey">{onlyFailed ? '실패 건이 없습니다 — 전부 통과.' : '검증 대상이 없습니다. KISA 데이터를 적재하세요.'}</td></tr>
              ) : (
                (data?.items ?? []).map((r, i) => (
                  <tr key={`${r.vehicle_no}-${i}`} className="border-b border-hairline/60">
                    <td className="px-2 py-2">
                      {r.status === 'PASS'
                        ? <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400"><CheckCircle size={15} weight="fill" />통과</span>
                        : <span className="inline-flex items-center gap-1 text-rose-500"><WarningCircle size={15} weight="fill" />실패</span>}
                    </td>
                    <td className="px-2 py-2 font-medium text-bone">{r.vehicle_no}</td>
                    <td className="px-2 py-2 text-ash">{r.client_name ?? r.operator_name ?? '—'}</td>
                    <td className="px-2 py-2 font-mono text-[11px] text-slatey">{r.old_vin ?? '—'} → {r.new_vin ?? '—'}</td>
                    <td className="px-2 py-2 text-ash">{r.old_fuel ?? '—'}</td>
                    <td className="px-2 py-2 text-xs text-rose-500">{r.reasons.join(', ') || '—'}</td>
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
