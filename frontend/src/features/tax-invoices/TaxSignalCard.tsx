// 경영 관찰 운영 신호 — 세금계산서 지표(순액·미연결 매출) 드릴다운 카드.
// 백엔드 신호 확장 없이 기존 tax 요약/정합성 API 재사용(읽기). 클릭 → 세금계산서 관리로.
import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Receipt, CaretRight } from '@phosphor-icons/react'
import { useTaxInvoiceIssueCounts, useTaxInvoiceSummary } from './api'

const nfKrw = (v: number) => {
  const a = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (a >= 1e8) return `${sign}${(a / 1e8).toFixed(1)}억`
  if (a >= 1e4) return `${sign}${Math.round(a / 1e4).toLocaleString('ko-KR')}만`
  return `${sign}${Math.round(a).toLocaleString('ko-KR')}`
}

function last12(): { date_from: string; date_to: string } {
  const now = new Date()
  const to = now.toISOString().slice(0, 10)
  const from = new Date(now.getFullYear(), now.getMonth() - 11, 1).toISOString().slice(0, 10)
  return { date_from: from, date_to: to }
}

export function TaxSignalCard() {
  const navigate = useNavigate()
  const range = useMemo(last12, [])
  const { data: summary } = useTaxInvoiceSummary(range)
  const { data: issues } = useTaxInvoiceIssueCounts({})

  const net = summary?.net_supply ?? 0
  const unlinked = issues?.unlinked ?? 0

  return (
    <section className="rounded-3xl border border-hairline bg-graphite p-4">
      <div className="mb-2 flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-xs font-medium text-ash">
          <Receipt size={14} weight="duotone" />
          세금계산서 (최근 12개월)
        </p>
        <button
          type="button"
          onClick={() => navigate('/tax-invoices')}
          className="flex items-center gap-0.5 text-[11px] font-semibold text-slatey hover:text-bone"
        >
          자세히 <CaretRight size={11} weight="bold" />
        </button>
      </div>
      <button
        type="button"
        onClick={() => navigate('/tax-invoices')}
        className="block w-full text-left"
      >
        <div className="flex items-baseline gap-1.5">
          <span
            className={`font-mono text-2xl font-bold tabular-nums ${
              net >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-500'
            }`}
          >
            {nfKrw(net)}
          </span>
          <span className="text-xs text-slatey">순액(매출−매입)</span>
        </div>
        <p className="mt-1 text-xs text-slatey">
          사업 미연결{' '}
          <span className={unlinked > 0 ? 'font-semibold text-amber-600 dark:text-amber-400' : 'text-ash'}>
            {unlinked}건
          </span>{' '}
          — 클릭하면 세금계산서 관리로
        </p>
      </button>
    </section>
  )
}
