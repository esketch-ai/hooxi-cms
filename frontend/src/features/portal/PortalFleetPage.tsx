// 포털 P1 — 내 회사 계약대수 월별 추이 (PARTNER 전용, read-only)
import { Bus, CircleNotch } from '@phosphor-icons/react'
import { usePortalFleet } from './api'

const INDUSTRY_LABEL: Record<string, string> = { CITY: '시내', RURAL: '농어촌', INTERCITY: '시외' }

export function PortalFleetPage() {
  const { data: items = [], isLoading } = usePortalFleet()

  if (isLoading) {
    return (
      <p className="flex items-center gap-1.5 text-sm text-ash">
        <CircleNotch size={15} className="animate-spin" />
        불러오는 중…
      </p>
    )
  }

  const evShare = (t: (typeof items)[number]) =>
    t.total_count && t.total_count > 0
      ? Math.round(((t.electric ?? 0) / t.total_count) * 1000) / 10
      : null

  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-lg font-bold text-bone">
          <Bus size={20} weight="fill" />
          계약대수 현황
        </h1>
        <p className="mt-0.5 text-sm text-slatey">
          월별 면허대수·차종 구성 — 매월 갱신됩니다.
        </p>
      </div>

      {items.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-hairline bg-graphite px-6 py-12 text-center text-sm text-slatey">
          아직 등록된 대수 현황이 없습니다.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-hairline">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="bg-elevate text-xs text-ash">
              <tr>
                <th className="px-3 py-2 font-medium">월</th>
                <th className="px-3 py-2 font-medium">업종</th>
                <th className="px-3 py-2 text-right font-medium">면허대수</th>
                <th className="px-3 py-2 text-right font-medium">경유</th>
                <th className="px-3 py-2 text-right font-medium">CNG</th>
                <th className="px-3 py-2 text-right font-medium">하이브리드</th>
                <th className="px-3 py-2 text-right font-medium">전기</th>
                <th className="px-3 py-2 text-right font-medium">수소</th>
                <th className="px-3 py-2 text-right font-medium">전기 비중</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {items.map((t) => (
                <tr key={t.period}>
                  <td className="px-3 py-2 font-mono text-xs text-bone">{t.period}</td>
                  <td className="px-3 py-2 text-xs text-slatey">
                    {t.industry ? (INDUSTRY_LABEL[t.industry] ?? t.industry) : '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums text-bone">
                    {t.license_count ?? '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums text-slatey">
                    {t.diesel ?? '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums text-slatey">
                    {t.cng ?? '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums text-slatey">
                    {t.hybrid ?? '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums font-semibold text-emerald-500">
                    {t.electric ?? '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums text-slatey">
                    {t.hydrogen ?? '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums text-ash">
                    {evShare(t) != null ? `${evShare(t)}%` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
