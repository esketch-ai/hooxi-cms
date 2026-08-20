// 포털 P1 — 내 회사 정산 내역(확정 이후) (PARTNER 전용, read-only)
import { CircleNotch, Wallet } from '@phosphor-icons/react'
import { usePortalSettlements } from './api'

const STATUS_LABEL: Record<string, { label: string; cls: string }> = {
  CONFIRMED: { label: '확정', cls: 'bg-sky-500/15 text-sky-700 dark:text-sky-300' },
  BILLED: { label: '청구', cls: 'bg-amber-500/15 text-amber-700 dark:text-amber-300' },
  COMPLETED: { label: '입금 완료', cls: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300' },
}

const fmtWon = (n?: number | null) =>
  n == null ? '—' : `${Math.round(n).toLocaleString('ko-KR')}원`

export function PortalSettlementsPage() {
  const { data: items = [], isLoading } = usePortalSettlements()

  if (isLoading) {
    return (
      <p className="flex items-center gap-1.5 text-sm text-ash">
        <CircleNotch size={15} className="animate-spin" />
        불러오는 중…
      </p>
    )
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-lg font-bold text-bone">
          <Wallet size={20} weight="fill" />
          정산 내역
        </h1>
        <p className="mt-0.5 text-sm text-slatey">
          확정된 정산의 진행 상태(확정 → 청구 → 입금)를 확인할 수 있습니다.
        </p>
      </div>

      {items.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-hairline bg-graphite px-6 py-12 text-center text-sm text-slatey">
          확정된 정산이 아직 없습니다.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-hairline">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="bg-elevate text-xs text-ash">
              <tr>
                <th className="px-3 py-2 font-medium">사업</th>
                <th className="px-3 py-2 font-medium">기간</th>
                <th className="px-3 py-2 font-medium">상태</th>
                <th className="px-3 py-2 text-right font-medium">확정 금액</th>
                <th className="px-3 py-2 text-right font-medium">차량 대수</th>
                <th className="px-3 py-2 text-right font-medium">입금액</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {items.map((s) => {
                const st = STATUS_LABEL[s.status] ?? {
                  label: s.status,
                  cls: 'bg-elevate-strong text-ash',
                }
                return (
                  <tr key={s.settlement_id}>
                    <td className="max-w-[220px] truncate px-3 py-2 text-bone">
                      {s.project_name ?? '—'}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-slatey">{s.period ?? '—'}</td>
                    <td className="px-3 py-2">
                      <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${st.cls}`}>
                        {st.label}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-bone">
                      {fmtWon(s.confirmed_amount)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-slatey">
                      {s.vehicle_count ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-emerald-600 dark:text-emerald-400">
                      {fmtWon(s.paid_amount)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
