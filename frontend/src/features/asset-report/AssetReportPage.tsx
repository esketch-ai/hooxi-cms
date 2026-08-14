// P2 자산관리 보고 — 운수사(고객사)별 정산 예정 요약. 부서 엑셀 보고의 시스템 대체.
// cf. FL-3 재무 원장은 '사업 grain', 여기는 '고객사 grain' — 참여사업·차량·예상지급액 집계(subtitle로 구분).
import { useMemo, useState } from 'react'
import { CheckCircle, Coins, DownloadSimple, TreeStructure, Truck } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { FilterBar, FilterSelect } from '../../components/FilterBar'
import { DataTable, type Column } from '../../components/DataTable'
import { KpiCard } from '../../components/KpiCard'
import { SensitiveData } from '../../components/SensitiveData'
import { EmptyState } from '../../components/EmptyState'
import { RoleGate } from '../../components/RoleGate'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import { useCodes, useClientOptions } from '../../lib/api/queries'
import { downloadExport } from '../../lib/export'
import { fmtMoney } from '../../lib/format'
import { useSettlementSummary } from './api'
import type { SettlementSummaryRow } from './types'

/** 정수(참여수량·감축량 tCO₂ 등) 포맷 — nullable */
function fmtQty(value?: number | null, unit = ''): string {
  if (value === null || value === undefined) return '—'
  return `${Number(value).toLocaleString('ko-KR')}${unit}`
}

/** 금액 셀 — 값 있으면 SensitiveData(money), 없으면 '미정' 대시 */
function MoneyCell({ value }: { value: number | null }) {
  return value != null ? (
    <SensitiveData type="money" value={fmtMoney(value)} />
  ) : (
    <span className="text-smoke">미정</span>
  )
}

export function AssetReportPage() {
  const { user } = useAuth()
  const { showToast } = useToast()
  // OBSERVER(경영전략실)는 정책 A로 /clients가 백엔드 403 → 운수사 셀렉트 숨김 + 훅 미호출.
  const isObserver = user?.role === 'OBSERVER'
  const { data: clients = [] } = useClientOptions({ enabled: !isObserver })
  const { labelOf: clientTypeLabel, options: clientTypeOptions } = useCodes('CLIENT_TYPE')
  const { options: regionOptions } = useCodes('REGION')

  // 엑셀 내보내기 — 팀장 이상만(백엔드 require_role("MANAGER")과 정합). OBSERVER·STAFF엔 미노출.
  const isManagerUp = user?.role === 'ADMIN' || user?.role === 'MANAGER'
  const [exporting, setExporting] = useState(false)

  const [clientType, setClientType] = useState('')
  const [region, setRegion] = useState('')
  const [clientId, setClientId] = useState('')
  const [expandedId, setExpandedId] = useState('') // 행 펼침(운수사) 드릴다운

  const filters = useMemo(
    () => ({
      client_type: clientType,
      region,
      client_id: clientId,
    }),
    [clientType, region, clientId],
  )

  const { data, isLoading, isError, refetch } = useSettlementSummary(filters)
  const rows = data?.items ?? []
  const total = data?.total ?? 0
  const totals = data?.totals

  async function handleExport() {
    if (exporting) return
    setExporting(true)
    try {
      await downloadExport('/asset-report/settlement-summary/export', filters, '자산관리보고.xlsx')
      showToast('엑셀 내보내기를 시작했습니다.', 'success')
    } catch (err) {
      showToast(err instanceof Error ? err.message : '내보내기에 실패했습니다.', 'danger')
    } finally {
      setExporting(false)
    }
  }

  const columns: Column<SettlementSummaryRow>[] = [
    {
      key: 'company_name',
      header: '운수사',
      className: 'min-w-[180px]',
      render: (v) => (
        <span className="font-semibold text-bone">{v.company_name ?? '미매칭'}</span>
      ),
    },
    {
      key: 'client_type',
      header: '구분',
      render: (v) => (
        <span className="text-sm text-ash">{v.client_type ? clientTypeLabel(v.client_type) : '—'}</span>
      ),
    },
    {
      key: 'region',
      header: '지역',
      render: (v) => <span className="text-sm text-ash">{v.region ?? '—'}</span>,
    },
    {
      key: 'participating_project_count',
      header: '참여사업수',
      className: 'text-right',
      render: (v) => <span className="text-sm text-bone">{fmtQty(v.participating_project_count)}</span>,
    },
    {
      key: 'participating_vehicle_count',
      header: '참여차량수',
      className: 'text-right',
      render: (v) => <span className="text-sm text-bone">{fmtQty(v.participating_vehicle_count)}</span>,
    },
    {
      key: 'total_reduction',
      header: '총감축량',
      className: 'text-right',
      render: (v) => <span className="text-sm text-ash">{fmtQty(v.total_reduction, ' tCO₂')}</span>,
    },
    {
      key: 'effective_reduction',
      header: '잔여반영감축량',
      className: 'text-right',
      render: (v) => <span className="text-sm text-ash">{fmtQty(v.effective_reduction, ' tCO₂')}</span>,
    },
    {
      key: 'expected_payout',
      header: '예상지급액(정산예정)',
      className: 'text-right',
      render: (v) => <MoneyCell value={v.expected_payout} />,
    },
  ]

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="자산관리 보고"
        subtitle="운수사별 정산 예정 요약 — 고객사 단위 (cf. 재무 원장은 사업 단위)"
        actions={
          <RoleGate allow={isManagerUp} reason="엑셀 내보내기는 팀장 이상만 가능합니다.">
            <button
              type="button"
              onClick={handleExport}
              disabled={exporting}
              className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate disabled:cursor-not-allowed disabled:opacity-50"
            >
              <DownloadSimple size={16} />
              {exporting ? '내보내는 중…' : '엑셀 내보내기'}
            </button>
          </RoleGate>
        }
      />

      {/* 전사 총계 KPI — 필터 기준 전 운수사 합 (사업수는 distinct, 금액 SensitiveData money) */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          title="참여 사업수"
          value={fmtQty(totals?.distinct_project_count)}
          sub="필터 기준 distinct 합"
          icon={<TreeStructure size={18} />}
          variant="dark"
        />
        <KpiCard
          title="참여 차량수"
          value={fmtQty(totals?.participating_vehicle_count)}
          sub="필터 기준 전 운수사 합"
          icon={<Truck size={18} />}
          variant="dark"
        />
        <KpiCard
          title="잔여반영감축량"
          value={fmtQty(totals?.effective_reduction, ' tCO₂')}
          sub={`총감축량 ${fmtQty(totals?.total_reduction, ' tCO₂')}`}
          icon={<CheckCircle size={18} />}
          variant="dark"
        />
        <KpiCard
          title="예상지급액(정산예정)"
          value={<SensitiveData type="money" value={fmtMoney(totals?.expected_payout ?? null)} />}
          sub="필터 기준 전 운수사 합"
          icon={<Coins size={18} />}
          variant="dark"
        />
      </div>

      <FilterBar>
        <FilterSelect
          label="구분"
          value={clientType}
          onChange={setClientType}
          options={clientTypeOptions}
        />
        <FilterSelect label="지역" value={region} onChange={setRegion} options={regionOptions} />
        {/* 운수사 필터는 /clients 의존 — OBSERVER는 차단 대상이라 숨김(훅도 enabled:false) */}
        {!isObserver && (
          <FilterSelect
            label="운수사"
            value={clientId}
            onChange={setClientId}
            options={clients.map((c) => ({ value: c.client_id, label: c.company_name }))}
          />
        )}
      </FilterBar>

      {isError ? (
        <EmptyState
          icon={<Coins size={36} />}
          title="정산 요약을 불러오지 못했습니다"
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
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(v) => v.client_id ?? `unmatched:${v.company_name ?? ''}`}
          onRowClick={(v) => {
            const key = v.client_id ?? `unmatched:${v.company_name ?? ''}`
            setExpandedId((prev) => (prev === key ? '' : key))
          }}
          expandedKey={expandedId}
          renderExpanded={(v) => <ProjectBreakdownPanel row={v} />}
          isLoading={isLoading}
          emptyTitle="해당 조건의 운수사가 없습니다"
          emptyDescription="필터를 조정해 주세요."
        />
      )}

      {total > 0 && (
        <p className="px-1 text-xs text-slatey">총 {fmtQty(total)} 개 운수사</p>
      )}
    </div>
  )
}

/** 행 펼침 상세 — 해당 운수사가 참여한 사업별 브레이크다운(사업명·차량수·감축량·예상지급액) */
function ProjectBreakdownPanel({ row }: { row: SettlementSummaryRow }) {
  if (row.projects.length === 0) {
    return <p className="text-sm text-slatey">참여 사업 내역이 없습니다.</p>
  }
  return (
    <div className="space-y-2 text-sm">
      <h4 className="text-xs font-semibold tracking-wide text-ash">참여 사업 내역</h4>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse">
          <thead>
            <tr className="border-b border-hairline text-left text-xs text-slatey">
              <th className="py-1.5 pr-4 font-medium">사업명</th>
              <th className="py-1.5 pr-4 text-right font-medium">차량수</th>
              <th className="py-1.5 pr-4 text-right font-medium">총감축량</th>
              <th className="py-1.5 pr-4 text-right font-medium">잔여반영감축량</th>
              <th className="py-1.5 text-right font-medium">예상지급액</th>
            </tr>
          </thead>
          <tbody>
            {row.projects.map((p) => (
              <tr key={p.project_id} className="border-b border-hairline/60">
                <td className="py-1.5 pr-4 text-bone">{p.project_name ?? '—'}</td>
                <td className="py-1.5 pr-4 text-right text-ash">{fmtQty(p.vehicle_count)}</td>
                <td className="py-1.5 pr-4 text-right text-ash">{fmtQty(p.total_reduction, ' tCO₂')}</td>
                <td className="py-1.5 pr-4 text-right text-ash">
                  {fmtQty(p.effective_reduction, ' tCO₂')}
                </td>
                <td className="py-1.5 text-right">
                  <MoneyCell value={p.expected_payout} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
