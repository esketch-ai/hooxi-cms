// SCR-07 고객사별 정산 현황 — "누구에게 얼마를 청구했고, 입금이 어디까지 됐는가"
import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Coins, Receipt } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { FilterBar, FilterSelect } from '../../components/FilterBar'
import { DataTable, type Column } from '../../components/DataTable'
import { Pagination } from '../../components/Pagination'
import { StatusBadge } from '../../components/StatusBadge'
import { SensitiveData } from '../../components/SensitiveData'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { EmptyState } from '../../components/EmptyState'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import { fmtMoney, fmtServerDate, parseServerUtc } from '../../lib/format'
import type { ProjectClientMap, SettlementStatus } from '../../types'
import { useProjectOptions } from '../projects/api'
import { useSettlements, useUpdateSettlementStatus } from './api'

const PAGE_SIZE = 20

/** 청구 후 30일 이상 미입금 여부 (SCR-07 §6) */
function isOverdueBilled(row: ProjectClientMap): boolean {
  if (row.settlement_status !== 'BILLED' || !row.billed_at) return false
  const billed = parseServerUtc(row.billed_at)
  if (Number.isNaN(billed.getTime())) return false
  return Date.now() - billed.getTime() > 30 * 86_400_000
}

/** 상태 배지 + 기준 일자 서브라인 */
function SettlementStatusCell({ row }: { row: ProjectClientMap }) {
  const overdue = isOverdueBilled(row)
  let sub: string | null = null
  if (row.settlement_status === 'BILLED' && row.billed_at) {
    sub = `청구 ${fmtServerDate(row.billed_at)}`
  } else if (row.settlement_status === 'COMPLETED' && row.completed_at) {
    sub = `입금 ${fmtServerDate(row.completed_at)}`
  }
  return (
    <div>
      <StatusBadge domain="settlement" value={row.settlement_status ?? 'STANDBY'} />
      {sub && (
        <p className={`mt-1 text-xs ${overdue ? 'font-semibold text-rose-700 dark:text-rose-300' : 'text-slatey'}`}>
          {sub}
          {overdue && ' · 30일+ 미입금'}
        </p>
      )}
    </div>
  )
}

interface PendingAction {
  row: ProjectClientMap
  next: SettlementStatus
}

export function SettlementsPage() {
  const { user } = useAuth()
  const { showToast } = useToast()
  // 상태 변경·발행은 MANAGER 이상 (§10.1) — 미만이면 버튼 숨김
  const canManage = user?.role === 'MANAGER' || user?.role === 'ADMIN'

  const [searchParams] = useSearchParams()
  const { data: projects = [] } = useProjectOptions()

  const [status, setStatus] = useState('')
  // SCR-06 관리 열의 '정산 매핑' 딥링크(?project_id=) 수신
  const [projectId, setProjectId] = useState(searchParams.get('project_id') ?? '')
  const [period, setPeriod] = useState('')
  const [page, setPage] = useState(1)
  const [pending, setPending] = useState<PendingAction | null>(null)

  const filters = useMemo(
    () => ({ settlement_status: status, project_id: projectId, period, page, page_size: PAGE_SIZE }),
    [status, projectId, period, page],
  )

  const { data, isLoading, isError, refetch } = useSettlements(filters)
  const rows = data?.items ?? []
  const total = data?.total ?? 0

  // 대표자/참여자 — tb_project.client_id 일치 여부 (사업 옵션 목록에서 판정)
  const primaryClientByProject = useMemo(() => {
    const map = new Map<string, string>()
    projects.forEach((p) => {
      if (p.client_id) map.set(p.project_id, p.client_id)
    })
    return map
  }, [projects])
  const isPrimary = (r: ProjectClientMap) =>
    primaryClientByProject.get(r.project_id) === r.client_id

  // 합계 요약 — 현재 페이지 합계 (서버 집계 필드 미제공)
  const summaryCount = total
  const summaryExpected = rows.reduce((acc, r) => acc + (Number(r.expected_amount) || 0), 0)

  const updateStatus = useUpdateSettlementStatus()

  const confirmAction = async () => {
    if (!pending) return
    try {
      await updateStatus.mutateAsync({ mapId: pending.row.map_id, status: pending.next })
      showToast(
        pending.next === 'BILLED'
          ? '청구서 발행 처리되었습니다.'
          : '입금 완료 처리되었습니다.',
        'success',
      )
      setPending(null)
    } catch {
      showToast('상태 변경에 실패했습니다. 잠시 후 다시 시도해 주세요.', 'danger')
    }
  }

  /** 상태별 액션 — STANDBY→발행 / BILLED→입금 완료 / COMPLETED→읽기 전용 */
  const actionCell = (row: ProjectClientMap) => {
    if (!canManage) return <span className="text-xs text-slatey">—</span>
    if (row.settlement_status === 'STANDBY') {
      // 금액 미정(단가 NULL) 건은 발행 차단 (R2-A6)
      const blocked = row.expected_amount == null
      return (
        <button
          type="button"
          onClick={() => setPending({ row, next: 'BILLED' })}
          disabled={blocked}
          className="rounded-full border border-hairline px-2.5 py-1.5 text-xs font-semibold text-bone hover:bg-elevate disabled:cursor-not-allowed disabled:opacity-40"
          title={blocked ? '단가 미입력 — 금액 미정 건은 발행할 수 없습니다' : undefined}
        >
          청구서 발행
        </button>
      )
    }
    if (row.settlement_status === 'BILLED') {
      return (
        <button
          type="button"
          onClick={() => setPending({ row, next: 'COMPLETED' })}
          className="rounded-full bg-emerald-500/90 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500"
        >
          입금 완료 처리
        </button>
      )
    }
    return <span className="text-xs text-slatey">완료</span>
  }

  const columns: Column<ProjectClientMap>[] = [
    {
      key: 'client',
      header: '참여 고객사',
      render: (r) => (
        <div>
          <Link
            to={`/clients/${r.client_id}`}
            onClick={(e) => e.stopPropagation()}
            className="font-semibold text-bone hover:underline"
          >
            {r.client_name ?? '—'}
          </Link>
          <p className="text-xs text-slatey">{isPrimary(r) ? '대표자' : '참여자'}</p>
        </div>
      ),
    },
    {
      key: 'project',
      header: '감축 사업',
      render: (r) => (
        <div className="min-w-0">
          <Link
            to={`/projects/${r.project_id}`}
            onClick={(e) => e.stopPropagation()}
            className="block truncate text-sm text-bone hover:underline"
          >
            {r.project_name ?? '—'}
          </Link>
        </div>
      ),
    },
    {
      key: 'ratio',
      header: '지분율',
      render: (r) => (
        <span className="text-sm font-semibold text-bone">
          {r.allocation_ratio != null ? `${Number(r.allocation_ratio)} %` : '—'}
        </span>
      ),
    },
    {
      key: 'fee',
      header: '보수율',
      render: (r) =>
        r.success_fee_rate != null ? (
          <SensitiveData type="rate" value={`${Number(r.success_fee_rate)} %`} />
        ) : (
          <span className="text-slatey">—</span>
        ),
    },
    {
      key: 'amount',
      header: '예상 정산액',
      render: (r) =>
        r.expected_amount != null ? (
          <SensitiveData type="money" value={fmtMoney(Number(r.expected_amount))} />
        ) : (
          <span className="text-xs font-medium text-amber-700 dark:text-amber-300">미정</span>
        ),
    },
    {
      key: 'status',
      header: '정산 상태',
      render: (r) => <SettlementStatusCell row={r} />,
    },
    {
      key: 'actions',
      header: '관리',
      className: 'text-right',
      render: (r) => <div className="flex justify-end">{actionCell(r)}</div>,
    },
  ]

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader title="고객사별 정산 현황" subtitle="청구·입금 상태 추적 — 부서 공동 열람" />

      <FilterBar>
        <FilterSelect
          label="정산 상태"
          value={status}
          onChange={(v) => {
            setStatus(v)
            setPage(1)
          }}
          options={[
            { value: 'STANDBY', label: '대기' },
            { value: 'BILLED', label: '청구' },
            { value: 'COMPLETED', label: '입금완료' },
          ]}
        />
        <FilterSelect
          label="감축 사업"
          value={projectId}
          onChange={(v) => {
            setProjectId(v)
            setPage(1)
          }}
          options={projects.map((p) => ({ value: p.project_id, label: p.project_name }))}
        />
        <label className="flex items-center gap-1.5">
          <span className="shrink-0 text-xs font-medium text-ash">정산 기준월</span>
          <input
            type="month"
            value={period}
            onChange={(e) => {
              setPeriod(e.target.value)
              setPage(1)
            }}
            className="h-9 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
            aria-label="정산 기준월"
          />
        </label>
      </FilterBar>

      {/* 합계 요약 바 — 대상 건수·예상 정산액 합 🔒 */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-3xl border border-hairline bg-graphite px-4 py-3">
        <div className="flex items-center gap-2 text-sm">
          <Coins size={16} className="text-slatey" />
          <span className="text-ash">대상</span>
          <b className="text-bone">{summaryCount.toLocaleString('ko-KR')}건</b>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="text-ash">예상 정산액 합</span>
          <SensitiveData
            type="money"
            value={fmtMoney(summaryExpected)}
            className="font-bold text-bone"
          />
        </div>
        {total > rows.length && (
          <span className="text-xs text-slatey">(금액 합은 현재 페이지 기준)</span>
        )}
      </div>

      {isError ? (
        <EmptyState
          icon={<Receipt size={36} />}
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
            rowKey={(r) => r.map_id}
            isLoading={isLoading}
            emptyTitle="정산 대상이 없습니다"
            emptyDescription="감축 사업 상세에서 참여 고객사를 매핑하면 정산 건이 생성됩니다."
            renderCard={(r) => (
              /* 모바일 카드 — 열람 전용, 상태 변경 버튼 숨김 (SCR-07 §8) */
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <Link to={`/clients/${r.client_id}`} className="font-semibold text-bone">
                      {r.client_name ?? '—'}
                    </Link>
                    <p className="truncate text-xs text-slatey">
                      {isPrimary(r) ? '대표자' : '참여자'} · {r.project_name ?? '—'}
                    </p>
                  </div>
                  <SettlementStatusCell row={r} />
                </div>
                <div className="flex items-center justify-between border-t border-hairline pt-2 text-sm">
                  <span className="text-ash">
                    지분율{' '}
                    <b className="text-bone">
                      {r.allocation_ratio != null ? `${Number(r.allocation_ratio)} %` : '—'}
                    </b>
                  </span>
                  {r.expected_amount != null ? (
                    <SensitiveData type="money" value={fmtMoney(Number(r.expected_amount))} />
                  ) : (
                    <span className="text-xs font-medium text-amber-700 dark:text-amber-300">미정</span>
                  )}
                </div>
              </div>
            )}
          />
          {total > 0 && (
            <Pagination total={total} page={page} pageSize={PAGE_SIZE} onChange={setPage} />
          )}
        </>
      )}

      {/* 청구서 발행 / 입금 완료 확인 */}
      <ConfirmDialog
        open={!!pending}
        title={pending?.next === 'BILLED' ? '청구서 발행' : '입금 완료 처리'}
        message={
          pending && (
            <>
              <b>{pending.row.client_name ?? ''}</b> · {pending.row.project_name ?? ''}
              <br />
              예상 정산액{' '}
              <b>
                {pending.row.expected_amount != null ? (
                  /* 보안 모드 시 확인 다이얼로그에서도 금액 마스킹 (L-4) */
                  <SensitiveData
                    type="money"
                    value={fmtMoney(Number(pending.row.expected_amount))}
                  />
                ) : (
                  '미정'
                )}
              </b>
              {pending.next === 'BILLED'
                ? ' 건을 청구(BILLED) 상태로 전환합니다. 청구 시점 금액이 증빙으로 동결됩니다.'
                : ' 건을 입금 완료(COMPLETED) 처리합니다. 활동 이력에 자동 기록됩니다.'}
            </>
          )
        }
        confirmLabel={pending?.next === 'BILLED' ? '발행' : '입금 완료'}
        danger={pending?.next === 'BILLED'}
        loading={updateStatus.isPending}
        onConfirm={confirmAction}
        onCancel={() => setPending(null)}
      />
    </div>
  )
}
