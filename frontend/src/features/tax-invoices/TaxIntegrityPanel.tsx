// 세금계산서 정합성 워크리스트(경영전략실) — 붙일 것/확인할 것.
// 미연결(사업 미귀속)·미매칭(상대 마스터 없음)·음수(수정취소)를 골라 보고 조치 대상으로.
// 읽기 중심: 여기서 목록·근거를 확인하고 실무 담당자에게 넘긴다(정정은 기존 권한).
import { useState } from 'react'
import { CircleNotch, LinkBreak, UserFocus, ArrowUUpLeft } from '@phosphor-icons/react'
import { useTaxInvoiceIssueCounts, useTaxInvoices } from './api'

const won = (v?: number | null) =>
  v === null || v === undefined ? '—' : `${v.toLocaleString('ko-KR')}원`

type IssueKey = 'unlinked' | 'unmatched' | 'negative'

const CARDS: {
  key: IssueKey
  label: string
  desc: string
  icon: typeof LinkBreak
}[] = [
  { key: 'unlinked', label: '사업 미연결', desc: '감축사업에 안 붙은 매입·매출', icon: LinkBreak },
  { key: 'unmatched', label: '거래처 미매칭', desc: '운수사·투자사 마스터에 없는 상대', icon: UserFocus },
  { key: 'negative', label: '수정취소(음수)', desc: '공급가액이 음수인 정정분', icon: ArrowUUpLeft },
]

function DirBadge({ d }: { d?: string | null }) {
  const cls =
    d === '매입'
      ? 'bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-400/25'
      : d === '매출'
        ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-400/25'
        : 'bg-elevate-strong text-ash border-hairline'
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${cls}`}>
      {d ?? '미상'}
    </span>
  )
}

export function TaxIntegrityPanel() {
  const { data: counts, isLoading: countsLoading } = useTaxInvoiceIssueCounts({})
  const [issue, setIssue] = useState<IssueKey | null>(null)
  const [page, setPage] = useState(1)
  const pageSize = 50
  const { data: list, isLoading } = useTaxInvoices({
    issue: issue ?? undefined,
    page,
    page_size: pageSize,
  })

  const countOf = (k: IssueKey) => (counts ? counts[k] : undefined)
  const total = list?.total ?? 0
  const maxPage = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="space-y-4">
      <p className="text-sm font-semibold text-bone">
        정합성 점검{' '}
        <span className="font-normal text-slatey">· 전체 기간 · 카드를 눌러 목록을 확인하세요</span>
      </p>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {CARDS.map((c) => {
          const active = issue === c.key
          const n = countOf(c.key)
          return (
            <button
              key={c.key}
              type="button"
              onClick={() => {
                setIssue(active ? null : c.key)
                setPage(1)
              }}
              className={`rounded-2xl border p-4 text-left transition-colors ${
                active
                  ? 'border-primary/60 bg-elevate-strong'
                  : 'border-hairline bg-graphite hover:bg-elevate'
              }`}
            >
              <div className="flex items-center justify-between">
                <c.icon
                  size={18}
                  className={n && n > 0 ? 'text-amber-500' : 'text-slatey'}
                  weight="duotone"
                />
                <span
                  className={`text-2xl font-bold tabular-nums ${
                    n && n > 0 ? 'text-bone' : 'text-slatey'
                  }`}
                >
                  {countsLoading ? '…' : (n ?? 0)}
                </span>
              </div>
              <p className="mt-1.5 text-sm font-semibold text-bone">{c.label}</p>
              <p className="text-[11px] leading-tight text-slatey">{c.desc}</p>
            </button>
          )
        })}
      </div>

      {issue === null ? (
        <div className="rounded-2xl border border-dashed border-hairline p-8 text-center text-sm text-slatey">
          위 카드를 선택하면 해당 항목 목록이 표시됩니다. 확인 후 실무 담당자에게 사업 연결·마스터
          등록을 요청하세요.
        </div>
      ) : (
        <section className="rounded-2xl border border-hairline bg-graphite p-5">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-bone">
              {CARDS.find((c) => c.key === issue)?.label} — {total}건
            </p>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-sm">
              <thead className="border-b border-hairline text-[11px] uppercase tracking-wider text-slatey">
                <tr>
                  <th className="px-2 py-2">작성일</th>
                  <th className="px-2 py-2">방향</th>
                  <th className="px-2 py-2">공급자 → 받는자</th>
                  <th className="px-2 py-2">상대</th>
                  <th className="px-2 py-2 text-right">공급가액</th>
                  <th className="px-2 py-2">승인번호</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={6} className="px-2 py-8 text-center text-ash">
                      <CircleNotch size={16} className="mx-auto animate-spin" />
                    </td>
                  </tr>
                ) : (list?.items ?? []).length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-2 py-8 text-center text-slatey">
                      해당 항목이 없습니다 — 정합성 양호.
                    </td>
                  </tr>
                ) : (
                  (list?.items ?? []).map((r) => (
                    <tr key={r.tax_invoice_id} className="border-b border-hairline/60">
                      <td className="px-2 py-2 text-ash">{r.issue_date ?? '—'}</td>
                      <td className="px-2 py-2">
                        <DirBadge d={r.direction} />
                      </td>
                      <td className="px-2 py-2 text-bone">
                        {r.invoicer_name ?? r.invoicer_reg_no} →{' '}
                        {r.invoicee_name ?? r.invoicee_reg_no}
                      </td>
                      <td className="px-2 py-2 text-ash">
                        {r.counterpart_name ?? '—'}
                        <span className="ml-1 font-mono text-[11px] text-slatey">
                          {r.counterpart_reg_no}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-right font-medium text-bone">
                        {won(r.supply_amount)}
                      </td>
                      <td className="px-2 py-2 font-mono text-[11px] text-slatey">
                        {r.approval_no}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          {maxPage > 1 && (
            <div className="mt-3 flex items-center justify-end gap-2 text-sm">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="rounded-lg border border-hairline px-3 py-1.5 text-bone hover:bg-elevate disabled:opacity-40"
              >
                이전
              </button>
              <span className="text-ash">
                {page} / {maxPage}
              </span>
              <button
                type="button"
                disabled={page >= maxPage}
                onClick={() => setPage((p) => Math.min(maxPage, p + 1))}
                className="rounded-lg border border-hairline px-3 py-1.5 text-bone hover:bg-elevate disabled:opacity-40"
              >
                다음
              </button>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
