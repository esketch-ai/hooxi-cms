// FL-3 재무 원장 — 재무·회계(카본크레딧실)가 전 감축사업을 '사업 grain'으로 보는 원장.
// 엑셀(재고자산·미착품 관리)의 시스템 대체. cf. 전기버스 자산(AV-3)은 '차량 grain' — subtitle로 구분.
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Coins, Package, Receipt, TrendUp, Warehouse } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { FilterBar, FilterSearch, FilterSelect } from '../../components/FilterBar'
import { DataTable, type Column } from '../../components/DataTable'
import { Pagination } from '../../components/Pagination'
import { KpiCard } from '../../components/KpiCard'
import { SensitiveData } from '../../components/SensitiveData'
import { EmptyState } from '../../components/EmptyState'
import { useCodes, useClientOptions } from '../../lib/api/queries'
import { useBuyerOptions } from '../buyers/api'
import { fmtDate, fmtMoney } from '../../lib/format'
import { useFinanceLedger } from './api'
import type { FinanceLedgerRow } from './types'

const PAGE_SIZE = 20

/** 시세·재고평가용 원화 단가(원/tCO₂) 포맷 — ₩ 접두 없이 'N 원' */
function fmtWon(value?: number | null): string {
  if (value === null || value === undefined) return '—'
  return `${Number(value).toLocaleString('ko-KR')} 원`
}

/** 비율(0~1) → '12.5 %' — nullable */
function fmtPct(value?: number | null): string {
  if (value === null || value === undefined) return '—'
  const pct = Number(value) * 100
  // 소수 첫째 자리까지(정수면 정수) — 과도한 유효숫자 방지
  return `${Number.isInteger(pct) ? pct : pct.toFixed(1)} %`
}

/** 소유권비율(이미 퍼센트 0~100) → 'N %' — ×100 하지 않음 */
function fmtOwnPct(value?: number | null): string {
  if (value === null || value === undefined) return '—'
  const v = Number(value)
  return `${Number.isInteger(v) ? v : v.toFixed(2)} %`
}

/** 정수(수량 tCO₂ 등) 포맷 — nullable */
function fmtQty(value?: number | null, unit = ''): string {
  if (value === null || value === undefined) return '—'
  return `${Number(value).toLocaleString('ko-KR')}${unit}`
}

/** 금액 셀 — 값 있으면 SensitiveData(money), 없으면 대시 */
function MoneyCell({ value }: { value: number | null }) {
  return value != null ? (
    <SensitiveData type="money" value={fmtMoney(value)} />
  ) : (
    <span className="text-smoke">—</span>
  )
}

export function FinanceLedgerPage() {
  const { data: clients = [] } = useClientOptions()
  const { data: buyers = [] } = useBuyerOptions()
  const { options: approvalStatusOptions } = useCodes('APPROVAL_STATUS')

  const [approvalStatus, setApprovalStatus] = useState('')
  const [clientId, setClientId] = useState('')
  const [buyerId, setBuyerId] = useState('')
  const [isHold, setIsHold] = useState('')
  const [invoiceFrom, setInvoiceFrom] = useState('')
  const [invoiceTo, setInvoiceTo] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [expandedId, setExpandedId] = useState('') // 행 펼침 상세

  // 필터 변경 시 1페이지로 리셋하는 setter 래퍼
  const resetPage =
    <T,>(setter: (v: T) => void) =>
    (v: T) => {
      setter(v)
      setPage(1)
    }

  const filters = useMemo(
    () => ({
      approval_status: approvalStatus,
      client_id: clientId,
      buyer_id: buyerId,
      is_hold: isHold,
      invoice_from: invoiceFrom,
      invoice_to: invoiceTo,
      search,
      page,
      page_size: PAGE_SIZE,
    }),
    [approvalStatus, clientId, buyerId, isHold, invoiceFrom, invoiceTo, search, page],
  )

  const { data, isLoading, isError, refetch } = useFinanceLedger(filters)
  const rows = data?.items ?? []
  const total = data?.total ?? 0
  const totals = data?.totals
  const marketRate = data?.current_market_rate ?? null

  const columns: Column<FinanceLedgerRow>[] = [
    {
      key: 'reg_code',
      header: '사업번호',
      render: (v) => <span className="font-mono text-sm text-bone">{v.reg_code ?? '—'}</span>,
    },
    {
      key: 'project',
      header: '사업명',
      className: 'min-w-[180px]',
      render: (v) => (
        <Link
          to={`/projects/${v.project_id}`}
          onClick={(e) => e.stopPropagation()}
          className="font-semibold text-bone hover:underline"
        >
          {v.project_name ?? '—'}
        </Link>
      ),
    },
    {
      key: 'approval_status',
      header: '승인상태',
      render: (v) => <span className="text-sm text-ash">{v.approval_status ?? '—'}</span>,
    },
    {
      key: 'product',
      header: '제품(총매입)',
      className: 'text-right',
      render: (v) => <MoneyCell value={v.product} />,
    },
    {
      key: 'expected_payment',
      header: '예상지급액',
      className: 'text-right',
      render: (v) => <MoneyCell value={v.expected_payment} />,
    },
    {
      key: 'inventory',
      header: '재고자산',
      className: 'text-right',
      render: (v) => <MoneyCell value={v.inventory} />,
    },
    {
      key: 'payout_rate',
      header: '지급률',
      className: 'text-right',
      render: (v) => <span className="text-sm text-ash">{fmtPct(v.payout_rate)}</span>,
    },
    {
      key: 'sale_recognized',
      header: '매출인식',
      className: 'text-right',
      render: (v) => <MoneyCell value={v.sale_recognized} />,
    },
    {
      key: 'gross_profit',
      header: '매출이익',
      className: 'text-right',
      render: (v) => <MoneyCell value={v.gross_profit} />,
    },
  ]

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="재무 원장"
        subtitle="전 감축사업 재무 집계 — 사업 단위 (cf. 전기버스 자산은 차량 단위)"
      />

      {/* 현재시세 배너 — 재고평가 기준 매출단가. 등록/변경은 환경설정으로 안내(입력 UI 중복 금지, 읽기만) */}
      <div className="flex flex-col gap-1.5 rounded-3xl border border-hairline bg-graphite-2 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2.5">
          <span className="text-slatey">
            <Coins size={18} />
          </span>
          <span className="text-sm text-ash">현재 매출단가 시세</span>
          <span className="text-lg font-bold tracking-tight text-bone">{fmtWon(marketRate)}</span>
          <span className="text-xs text-slatey">/ tCO₂</span>
        </div>
        <Link
          to="/settings"
          className="text-xs text-slatey underline decoration-hairline underline-offset-2 hover:text-ash"
        >
          시세 등록·변경은 환경설정 → 기준값·매출단가
        </Link>
      </div>

      {/* 총계 KPI — 필터 기준 전 사업 합 (금액 SensitiveData money) */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard
          title="매출인식"
          value={<SensitiveData type="money" value={fmtMoney(totals?.sale_recognized ?? null)} />}
          sub="필터 기준 전 사업 합"
          icon={<Receipt size={18} />}
          variant="dark"
        />
        <KpiCard
          title="제품(원가)"
          value={<SensitiveData type="money" value={fmtMoney(totals?.product ?? null)} />}
          sub="필터 기준 전 사업 합"
          icon={<Package size={18} />}
          variant="dark"
        />
        <KpiCard
          title="매출이익"
          value={<SensitiveData type="money" value={fmtMoney(totals?.gross_profit ?? null)} />}
          sub={`이익률 ${fmtPct(totals?.profit_rate)}`}
          icon={<TrendUp size={18} />}
          variant="dark"
        />
        <KpiCard
          title="재고자산"
          value={<SensitiveData type="money" value={fmtMoney(totals?.inventory ?? null)} />}
          sub="필터 기준 전 사업 합"
          icon={<Warehouse size={18} />}
          variant="dark"
        />
        <KpiCard
          title="재고평가"
          value={<SensitiveData type="money" value={fmtMoney(totals?.inventory_valuation ?? null)} />}
          sub="현재시세 기준"
          icon={<Coins size={18} />}
          variant="dark"
        />
      </div>

      <FilterBar>
        <FilterSelect
          label="승인상태"
          value={approvalStatus}
          onChange={resetPage(setApprovalStatus)}
          options={approvalStatusOptions}
        />
        <FilterSelect
          label="매수자"
          value={buyerId}
          onChange={resetPage(setBuyerId)}
          options={buyers.map((b) => ({ value: b.buyer_id, label: b.name }))}
        />
        <FilterSelect
          label="고객사"
          value={clientId}
          onChange={resetPage(setClientId)}
          options={clients.map((c) => ({ value: c.client_id, label: c.company_name }))}
        />
        <FilterSelect
          label="후시보유"
          value={isHold}
          onChange={resetPage(setIsHold)}
          options={[{ value: 'Y', label: '후시보유만' }]}
        />
        <label className="flex items-center gap-1.5">
          <span className="shrink-0 text-xs font-medium text-ash">계산서 발행일</span>
          <input
            type="date"
            value={invoiceFrom}
            onChange={(e) => resetPage(setInvoiceFrom)(e.target.value)}
            className="h-9 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
            aria-label="계산서 발행일 시작"
          />
          <span className="text-slatey">~</span>
          <input
            type="date"
            value={invoiceTo}
            onChange={(e) => resetPage(setInvoiceTo)(e.target.value)}
            className="h-9 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
            aria-label="계산서 발행일 종료"
          />
        </label>
        <FilterSearch
          value={search}
          onChange={resetPage(setSearch)}
          placeholder="사업명·사업번호 검색"
          className="min-w-[200px] flex-1"
        />
      </FilterBar>

      {isError ? (
        <EmptyState
          icon={<Receipt size={36} />}
          title="원장을 불러오지 못했습니다"
          description="네트워크 상태를 확인한 뒤 다시 시도해 주세요."
          action={
            <button
              type="button"
              onClick={() => refetch()}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
            >
              다시 시도
            </button>
          }
        />
      ) : (
        <>
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(v) => v.project_id}
            onRowClick={(v) =>
              setExpandedId((prev) => (prev === v.project_id ? '' : v.project_id))
            }
            expandedKey={expandedId}
            renderExpanded={(v) => <LedgerDetailPanel row={v} marketRate={marketRate} />}
            isLoading={isLoading}
            emptyTitle="해당 조건의 감축사업이 없습니다"
            emptyDescription="필터를 조정해 주세요."
          />
          {total > 0 && (
            <Pagination total={total} page={page} pageSize={PAGE_SIZE} onChange={setPage} />
          )}
        </>
      )}
    </div>
  )
}

/** 행 펼침 상세 — 회계 체인 잔여값 + 후시/계약 분할 + 재고평가(현재시세 기준) */
function LedgerDetailPanel({
  row,
  marketRate,
}: {
  row: FinanceLedgerRow
  marketRate: number | null
}) {
  return (
    <div className="space-y-5 text-sm">
      {/* 1. 회계 체인 (상시 컬럼 외 잔여값) */}
      <section>
        <h4 className="mb-2 text-xs font-semibold tracking-wide text-ash">회계 체인</h4>
        <div className="flex flex-wrap gap-x-6 gap-y-1.5">
          <span className="text-ash">
            미착품1 <span className="ml-1 text-bone"><MoneyCell value={row.wip1} /></span>
          </span>
          <span className="text-ash">
            미착품2 <span className="ml-1 text-bone"><MoneyCell value={row.wip2} /></span>
          </span>
          <span className="text-ash">
            부채 <span className="ml-1 text-bone"><MoneyCell value={row.liability} /></span>
          </span>
          <span className="text-ash">
            이익률 <span className="ml-1 text-bone">{fmtPct(row.profit_rate)}</span>
          </span>
        </div>
      </section>

      {/* 2. 후시/계약 분할 (D2 확정 — 상시 컬럼 아님) */}
      <section>
        <h4 className="mb-2 text-xs font-semibold tracking-wide text-ash">후시 · 계약 분할</h4>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          <div className="rounded-lg border border-hairline bg-elevate px-3 py-2">
            <div className="text-[10px] text-slatey">후시 보유량</div>
            <div className="mt-0.5 text-xs font-medium text-bone">
              {fmtQty(row.held_qty, ' tCO₂')}
            </div>
          </div>
          <div className="rounded-lg border border-hairline bg-elevate px-3 py-2">
            <div className="text-[10px] text-slatey">계약 판매량</div>
            <div className="mt-0.5 text-xs font-medium text-bone">
              {fmtQty(row.sold_qty, ' tCO₂')}
            </div>
          </div>
          <div className="rounded-lg border border-hairline bg-elevate px-3 py-2">
            <div className="text-[10px] text-slatey">후시 소유권비율</div>
            <div className="mt-0.5 text-xs font-medium text-bone">{fmtOwnPct(row.held_ownership)}</div>
          </div>
          <div className="rounded-lg border border-hairline bg-elevate px-3 py-2">
            <div className="text-[10px] text-slatey">계약 소유권비율</div>
            <div className="mt-0.5 text-xs font-medium text-bone">{fmtOwnPct(row.sold_ownership)}</div>
          </div>
          <div className="rounded-lg border border-hairline bg-elevate px-3 py-2">
            <div className="text-[10px] text-slatey">소유권비율합</div>
            <div className="mt-0.5 text-xs font-medium text-bone">{fmtOwnPct(row.ownership_total)}</div>
          </div>
        </div>
      </section>

      {/* 3. 재고평가 (현재시세 기준) */}
      <section>
        <h4 className="mb-2 text-xs font-semibold tracking-wide text-ash">재고평가</h4>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5">
          <span className="text-ash">
            재고평가액{' '}
            <span className="ml-1 text-bone">
              <MoneyCell value={row.inventory_valuation} />
            </span>
          </span>
          <span className="text-xs text-slatey">
            현재시세 {fmtWon(marketRate)} / tCO₂ 기준
          </span>
        </div>
      </section>
    </div>
  )
}
