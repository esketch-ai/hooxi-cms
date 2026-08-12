// AV-3 전기버스 자산 — 자산관리 크로스-프로젝트 차량 목록 + 필터 + KPI
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bus, ChartLineUp, Coins, Gauge } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { FilterBar, FilterSearch, FilterSelect } from '../../components/FilterBar'
import { DataTable, type Column } from '../../components/DataTable'
import { Pagination } from '../../components/Pagination'
import { KpiCard } from '../../components/KpiCard'
import { SensitiveData } from '../../components/SensitiveData'
import { EmptyState } from '../../components/EmptyState'
import { useCodes, useClientOptions } from '../../lib/api/queries'
import { useProject, useProjectOptions } from '../projects/api'
import { useBuyerOptions } from '../buyers/api'
import { fmtDate, fmtMoney } from '../../lib/format'
import { useAssetVehicles } from './api'
import type { AssetVehicleRow } from './types'

const PAGE_SIZE = 20

/** 감축량 포맷 'N tCO₂' — nullable */
function fmtReduction(value?: number | null): string {
  if (value === null || value === undefined) return '—'
  return `${Number(value).toLocaleString('ko-KR')} tCO₂`
}

/** 정수(대·년 등) 포맷 — nullable */
function fmtCount(value?: number | null, unit = ''): string {
  if (value === null || value === undefined) return '—'
  return `${Number(value).toLocaleString('ko-KR')}${unit}`
}

export function AssetVehiclesPage() {
  const { data: projects = [] } = useProjectOptions()
  const { data: clients = [] } = useClientOptions()
  const { data: buyers = [] } = useBuyerOptions()
  const { options: approvalStatusOptions } = useCodes('APPROVAL_STATUS')

  const [projectId, setProjectId] = useState('')
  const [region, setRegion] = useState('')
  const [clientId, setClientId] = useState('')
  const [approvalStatus, setApprovalStatus] = useState('')
  const [buyerId, setBuyerId] = useState('')
  const [registeredFrom, setRegisteredFrom] = useState('')
  const [registeredTo, setRegisteredTo] = useState('')
  const [expireBefore, setExpireBefore] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [expandedId, setExpandedId] = useState('') // AV-4 행 펼침 상세

  // 필터 변경 시 1페이지로 리셋하는 setter 래퍼
  const resetPage =
    <T,>(setter: (v: T) => void) =>
    (v: T) => {
      setter(v)
      setPage(1)
    }

  const filters = useMemo(
    () => ({
      project_id: projectId,
      region,
      client_id: clientId,
      approval_status: approvalStatus,
      buyer_id: buyerId,
      registered_from: registeredFrom,
      registered_to: registeredTo,
      expire_before: expireBefore,
      search,
      page,
      page_size: PAGE_SIZE,
    }),
    [
      projectId,
      region,
      clientId,
      approvalStatus,
      buyerId,
      registeredFrom,
      registeredTo,
      expireBefore,
      search,
      page,
    ],
  )

  const { data, isLoading, isError, refetch } = useAssetVehicles(filters)
  const rows = data?.items ?? []
  const total = data?.total ?? 0
  const kpi = data?.kpi

  // 운수사 옵션 — '__none__'(미지정) 선행 + 전체 고객사
  const clientOptions = useMemo(
    () => [
      { value: '__none__', label: '운수사 미지정' },
      ...clients.map((c) => ({ value: c.client_id, label: c.company_name })),
    ],
    [clients],
  )

  const columns: Column<AssetVehicleRow>[] = [
    {
      key: 'project',
      header: '프로젝트명',
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
      key: 'vehicle_no',
      header: '차량번호',
      render: (v) => <span className="font-mono text-sm text-bone">{v.vehicle_no ?? '—'}</span>,
    },
    {
      key: 'region',
      header: '지역',
      render: (v) => <span className="text-sm text-ash">{v.region ?? '—'}</span>,
    },
    {
      key: 'client',
      header: '운수사',
      render: (v) =>
        v.client_id ? (
          <Link
            to={`/clients/${v.client_id}`}
            onClick={(e) => e.stopPropagation()}
            className="text-sm text-bone hover:underline"
          >
            {v.client_name ?? '—'}
          </Link>
        ) : (
          <span className="text-xs text-slatey">미지정</span>
        ),
    },
    {
      key: 'registered_at',
      header: '차량등록일',
      render: (v) => <span className="text-sm text-ash">{fmtDate(v.registered_at)}</span>,
    },
    {
      key: 'expire_at',
      header: '차령만료일',
      render: (v) => <span className="text-sm text-ash">{fmtDate(v.expire_at)}</span>,
    },
    {
      key: 'approved_at',
      header: '사업승인일',
      render: (v) => <span className="text-sm text-ash">{fmtDate(v.approved_at)}</span>,
    },
    {
      key: 'total_reduction',
      header: '10년 총감축량',
      className: 'text-right',
      render: (v) => <span className="text-sm text-bone">{fmtReduction(v.total_reduction)}</span>,
    },
    {
      key: 'remaining_age',
      header: '잔여차령',
      className: 'text-right',
      render: (v) => <span className="text-sm text-ash">{fmtCount(v.remaining_age, '년')}</span>,
    },
    {
      key: 'effective_reduction',
      header: '잔여반영감축량',
      className: 'text-right',
      render: (v) => (
        <span className="text-sm text-bone">{fmtReduction(v.effective_reduction)}</span>
      ),
    },
    {
      key: 'expected_payout',
      header: '예상지급액',
      className: 'text-right',
      render: (v) =>
        v.expected_payout != null ? (
          <SensitiveData type="money" value={fmtMoney(v.expected_payout)} />
        ) : (
          <span className="text-smoke">—</span>
        ),
    },
    {
      key: 'project_revenue',
      header: '매출(사업)',
      className: 'text-right',
      render: (v) =>
        v.project_revenue != null ? (
          <SensitiveData type="money" value={fmtMoney(v.project_revenue)} />
        ) : (
          <span className="text-smoke">—</span>
        ),
    },
    {
      key: 'project_cost',
      header: '원가(사업)',
      className: 'text-right',
      render: (v) =>
        v.project_cost != null ? (
          <SensitiveData type="money" value={fmtMoney(v.project_cost)} />
        ) : (
          <span className="text-smoke">—</span>
        ),
    },
  ]

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="전기버스 자산"
        subtitle="자산관리 관점의 크로스-프로젝트 전기버스 차량 현황"
      />

      {/* 차량 KPI 4종 — 필터 걸린 차량 집계 */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          title="차량 수"
          value={fmtCount(kpi?.vehicle_count, '대')}
          icon={<Bus size={18} />}
        />
        <KpiCard
          title="10년 총감축량"
          value={fmtReduction(kpi?.total_reduction)}
          icon={<ChartLineUp size={18} />}
        />
        <KpiCard
          title="잔여반영감축량"
          value={fmtReduction(kpi?.effective_reduction_sum)}
          icon={<Gauge size={18} />}
        />
        <KpiCard
          title="예상 지급액 합계"
          value={
            <SensitiveData type="money" value={fmtMoney(kpi?.expected_payout_sum ?? null)} />
          }
          icon={<Coins size={18} />}
          variant="dark"
        />
      </div>

      {/* 재무 KPI 3종 — 관련 사업 전체 기준(차량 KPI와 그레인 다름, D2) */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <KpiCard
          title="매출"
          value={<SensitiveData type="money" value={fmtMoney(kpi?.revenue ?? null)} />}
          sub="관련 사업 전체 기준"
          variant="dark"
        />
        <KpiCard
          title="원가"
          value={<SensitiveData type="money" value={fmtMoney(kpi?.cost ?? null)} />}
          sub="관련 사업 전체 기준"
          variant="dark"
        />
        <KpiCard
          title="이익"
          value={<SensitiveData type="money" value={fmtMoney(kpi?.profit ?? null)} />}
          sub="관련 사업 전체 기준"
          variant="dark"
        />
      </div>

      <FilterBar>
        <FilterSelect
          label="프로젝트"
          value={projectId}
          onChange={resetPage(setProjectId)}
          options={projects.map((p) => ({ value: p.project_id, label: p.project_name }))}
        />
        <FilterSelect
          label="운수사"
          value={clientId}
          onChange={resetPage(setClientId)}
          options={clientOptions}
        />
        <FilterSelect
          label="승인상태"
          value={approvalStatus}
          onChange={resetPage(setApprovalStatus)}
          options={approvalStatusOptions}
        />
        <FilterSelect
          label="구매/투자사"
          value={buyerId}
          onChange={resetPage(setBuyerId)}
          options={buyers.map((b) => ({ value: b.buyer_id, label: b.name }))}
        />
        <label className="flex items-center gap-1.5">
          <span className="shrink-0 text-xs font-medium text-ash">등록일</span>
          <input
            type="date"
            value={registeredFrom}
            onChange={(e) => resetPage(setRegisteredFrom)(e.target.value)}
            className="h-9 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
            aria-label="등록일 시작"
          />
          <span className="text-slatey">~</span>
          <input
            type="date"
            value={registeredTo}
            onChange={(e) => resetPage(setRegisteredTo)(e.target.value)}
            className="h-9 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
            aria-label="등록일 종료"
          />
        </label>
        <label className="flex items-center gap-1.5">
          <span className="shrink-0 text-xs font-medium text-ash">차령만료 임박</span>
          <input
            type="date"
            value={expireBefore}
            onChange={(e) => resetPage(setExpireBefore)(e.target.value)}
            className="h-9 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
            aria-label="차령만료 임박 기준일"
          />
        </label>
        <label className="flex items-center gap-1.5">
          <span className="shrink-0 text-xs font-medium text-ash">지역</span>
          <input
            type="text"
            value={region}
            onChange={(e) => resetPage(setRegion)(e.target.value)}
            placeholder="예: 서울"
            className="h-9 w-24 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
            aria-label="지역"
          />
        </label>
        <FilterSearch
          value={search}
          onChange={resetPage(setSearch)}
          placeholder="차량번호·운수사명 검색"
          className="min-w-[200px] flex-1"
        />
      </FilterBar>

      {isError ? (
        <EmptyState
          icon={<Bus size={36} />}
          title="목록을 불러오지 못했습니다"
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
            rowKey={(v) => v.vehicle_id}
            onRowClick={(v) =>
              setExpandedId((prev) => (prev === v.vehicle_id ? '' : v.vehicle_id))
            }
            expandedKey={expandedId}
            renderExpanded={(v) => <VehicleDetailPanel row={v} />}
            isLoading={isLoading}
            emptyTitle="해당 조건의 전기버스 차량이 없습니다"
            emptyDescription="필터를 조정하거나 감축 사업에 차량을 등록해 주세요."
          />
          {total > 0 && (
            <Pagination total={total} page={page} pageSize={PAGE_SIZE} onChange={setPage} />
          )}
        </>
      )}
    </div>
  )
}

/** AV-4 행 펼침 상세 — 연차별 감축량·프로젝트 상태·계약/소유권(지연조회)·증빙(준비중) */
function VehicleDetailPanel({ row }: { row: AssetVehicleRow }) {
  // 계약·소유권은 행 데이터에 없어 소속 사업 상세를 지연 조회(react-query 캐시 재사용)
  const { data: project, isLoading: salesLoading } = useProject(row.project_id)
  const sales = project?.sales ?? []

  const years: (number | null)[] = [
    row.reduction_y1,
    row.reduction_y2,
    row.reduction_y3,
    row.reduction_y4,
    row.reduction_y5,
    row.reduction_y6,
    row.reduction_y7,
    row.reduction_y8,
    row.reduction_y9,
    row.reduction_y10,
  ]

  return (
    <div className="space-y-5 text-sm">
      {/* 1. 연차별 감축량 (1~10년차) */}
      <section>
        <h4 className="mb-2 text-xs font-semibold tracking-wide text-ash">연차별 감축량</h4>
        <div className="grid grid-cols-5 gap-2 sm:grid-cols-10">
          {years.map((val, i) => (
            <div
              key={i}
              className="rounded-lg border border-hairline bg-elevate px-2 py-1.5 text-center"
            >
              <div className="text-[10px] text-slatey">{i + 1}년차</div>
              <div className="mt-0.5 text-xs font-medium text-bone">
                {val === null || val === undefined
                  ? '—'
                  : `${Number(val).toLocaleString('ko-KR')} tCO₂`}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 2. 프로젝트 상태 */}
      <section>
        <h4 className="mb-2 text-xs font-semibold tracking-wide text-ash">프로젝트 상태</h4>
        <div className="flex flex-wrap gap-x-6 gap-y-1.5">
          <span className="text-ash">
            진행상태 <span className="ml-1 text-bone">{row.project_status ?? '—'}</span>
          </span>
          <span className="text-ash">
            승인상태 <span className="ml-1 text-bone">{row.approval_status ?? '—'}</span>
          </span>
          <span className="text-ash">
            승인일 <span className="ml-1 text-bone">{fmtDate(row.approved_at)}</span>
          </span>
        </div>
      </section>

      {/* 3. 계약·소유권 (지연 조회) */}
      <section>
        <h4 className="mb-2 text-xs font-semibold tracking-wide text-ash">계약·소유권</h4>
        {salesLoading ? (
          <div className="text-xs text-slatey">거래계약을 불러오는 중…</div>
        ) : sales.length === 0 ? (
          <div className="text-xs text-slatey">등록된 거래계약 없음</div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-hairline">
            <table className="w-full min-w-max text-left text-xs">
              <thead>
                <tr className="border-b border-hairline bg-elevate text-ash">
                  <th className="px-3 py-2 font-semibold">매수자</th>
                  <th className="px-3 py-2 text-right font-semibold">소유비율</th>
                  <th className="px-3 py-2 text-right font-semibold">적용단가</th>
                  <th className="px-3 py-2 text-center font-semibold">후시보유</th>
                </tr>
              </thead>
              <tbody>
                {sales.map((s) => (
                  <tr key={s.sale_id} className="border-b border-hairline/60 last:border-b-0">
                    <td className="px-3 py-2 font-medium text-bone">{s.buyer_name}</td>
                    <td className="px-3 py-2 text-right text-ash">
                      {s.ownership_pct != null ? `${Number(s.ownership_pct)} %` : '—'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {s.sale_unit_price != null ? (
                        <SensitiveData type="money" value={fmtMoney(Number(s.sale_unit_price))} />
                      ) : (
                        <span className="text-slatey">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-center">
                      {s.is_hold === 'Y' ? (
                        <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-300">
                          후시보유
                        </span>
                      ) : (
                        <span className="text-slatey">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* 4. 증빙문서 (P1 준비중 플레이스홀더) */}
      <section>
        <h4 className="mb-2 text-xs font-semibold tracking-wide text-ash">증빙문서</h4>
        <div className="text-xs text-slatey">증빙 첨부는 준비 중입니다.</div>
      </section>
    </div>
  )
}
