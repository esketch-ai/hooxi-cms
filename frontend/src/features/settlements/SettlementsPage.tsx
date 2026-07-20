// SCR-07 고객사별 정산 현황 — "누구에게 얼마를 청구했고, 입금이 어디까지 됐는가"
import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CircleNotch, ClockCounterClockwise, Coins, Receipt } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { FilterBar, FilterSelect } from '../../components/FilterBar'
import { DataTable, type Column } from '../../components/DataTable'
import { Pagination } from '../../components/Pagination'
import { StatusBadge } from '../../components/StatusBadge'
import { SensitiveData } from '../../components/SensitiveData'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { EmptyState } from '../../components/EmptyState'
import { Modal } from '../../components/Modal'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import { useCodes } from '../../lib/api/queries'
import { fmtMoney, fmtServerDate, fmtServerDateTime, parseServerUtc } from '../../lib/format'
import type { ProjectClientMap, SettlementStatus } from '../../types'
import { useProjectOptions } from '../projects/api'
import { useSettlementSnapshots, useSettlements, useUpdateSettlementStatus } from './api'

const PAGE_SIZE = 20

/** 스냅샷 회차 액션 배지 — REBILLED/REVERTED는 SETTLEMENT_STATUS 코드가 아니므로 로컬 사전 */
const SNAPSHOT_ACTIONS: Record<string, { label: string; className: string }> = {
  BILLED: {
    label: '청구',
    className: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-400/25',
  },
  REBILLED: {
    label: '재청구',
    className: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-400/25',
  },
  REVERTED: {
    label: '청구 취소',
    className: 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-400/25',
  },
  COMPLETED: {
    label: '입금완료',
    className: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-400/25',
  },
}

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

  const { options: settlementStatusOptions } = useCodes('SETTLEMENT_STATUS')
  const [status, setStatus] = useState('')
  // SCR-06 관리 열의 '정산 매핑' 딥링크(?project_id=) 수신
  const [projectId, setProjectId] = useState(searchParams.get('project_id') ?? '')
  const [period, setPeriod] = useState('')
  const [page, setPage] = useState(1)
  const [pending, setPending] = useState<PendingAction | null>(null)
  // 회차 스냅샷 이력 모달 대상 행 — 청구 시점 동결 금액 조회 (R3-1)
  const [historyRow, setHistoryRow] = useState<ProjectClientMap | null>(null)

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

  /** 회차 이력 버튼 — 스냅샷은 상태 전이 시에만 생기므로 STANDBY(스냅샷 0)는 숨김. 열람은 전 직급 */
  const historyButton = (row: ProjectClientMap) => {
    if (!row.settlement_status || row.settlement_status === 'STANDBY') return null
    return (
      <button
        type="button"
        onClick={() => setHistoryRow(row)}
        className="flex items-center gap-1 rounded-full border border-hairline px-2.5 py-1.5 text-xs font-medium text-bone hover:bg-elevate"
        title="청구/입금 시점에 동결된 금액 이력을 조회합니다"
      >
        <ClockCounterClockwise size={13} />
        이력
      </button>
    )
  }

  /** 상태별 액션 — STANDBY→발행 / BILLED→입금 완료 / COMPLETED→읽기 전용(+회차 이력) */
  const actionCell = (row: ProjectClientMap) => {
    if (!canManage) {
      // 막다른 정보 방지 — 처리 가능한 상태면 왜 버튼이 없는지(권한)를 보여준다
      const history = historyButton(row)
      const actionable =
        row.settlement_status === 'STANDBY' || row.settlement_status === 'BILLED'
      return (
        <>
          {history}
          {actionable ? (
            <span
              className="text-xs text-slatey"
              title="청구서 발행·입금 처리는 팀장(MANAGER) 이상이 할 수 있습니다"
            >
              팀장 권한
            </span>
          ) : (
            !history && <span className="text-xs text-slatey">—</span>
          )}
        </>
      )
    }
    if (row.settlement_status === 'STANDBY') {
      // 금액 미정(단가 NULL) 건은 발행 불가 (R2-A6) — 비활성 버튼 대신 해결 동선으로 직행
      if (row.expected_amount == null) {
        return (
          <Link
            to={`/projects/${row.project_id}`}
            onClick={(e) => e.stopPropagation()}
            className="rounded-full border border-amber-400/40 px-2.5 py-1.5 text-xs font-semibold text-amber-700 hover:bg-amber-500/10 dark:text-amber-300"
            title="배출권 단가가 없어 청구할 수 없습니다 — 사업 상세에서 단가를 입력하면 발행 버튼이 활성화됩니다"
          >
            단가 입력 →
          </Link>
        )
      }
      return (
        <button
          type="button"
          onClick={() => setPending({ row, next: 'BILLED' })}
          className="rounded-full border border-hairline px-2.5 py-1.5 text-xs font-semibold text-bone hover:bg-elevate"
        >
          청구서 발행
        </button>
      )
    }
    if (row.settlement_status === 'BILLED') {
      return (
        <>
          {historyButton(row)}
          <button
            type="button"
            onClick={() => setPending({ row, next: 'COMPLETED' })}
            className="rounded-full bg-emerald-500/90 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500"
          >
            입금 완료 처리
          </button>
        </>
      )
    }
    return (
      <>
        {historyButton(row)}
        <span className="text-xs text-slatey">완료</span>
      </>
    )
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
      render: (r) => <div className="flex items-center justify-end gap-1.5">{actionCell(r)}</div>,
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
          options={settlementStatusOptions}
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
        {/* 상태 흐름 안내 — "어디서 어떻게 바뀌는가"를 화면이 스스로 설명 */}
        <div
          className="flex items-center gap-1.5 text-xs text-slatey sm:ml-auto"
          title={
            canManage
              ? '상태 변경은 각 행 오른쪽의 버튼으로 진행합니다. 청구 시점 금액은 동결되며, 역순 변경은 불가합니다.'
              : '청구서 발행·입금 처리는 팀장(MANAGER) 이상이 각 행의 버튼으로 진행합니다.'
          }
        >
          <StatusBadge domain="settlement" value="STANDBY" />
          <span aria-hidden>→</span>
          <span className="rounded-md border border-hairline bg-elevate px-1.5 py-0.5 font-medium text-ash">
            청구서 발행
          </span>
          <span aria-hidden>→</span>
          <StatusBadge domain="settlement" value="BILLED" />
          <span aria-hidden>→</span>
          <span className="rounded-md border border-hairline bg-elevate px-1.5 py-0.5 font-medium text-ash">
            입금 완료
          </span>
          <span aria-hidden>→</span>
          <StatusBadge domain="settlement" value="COMPLETED" />
          {!canManage && <span className="ml-1">(팀장 이상)</span>}
        </div>
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

      {/* 회차 스냅샷 이력 — 청구/입금 시점 동결 금액의 정본 (R3-1) */}
      <SnapshotHistoryModal row={historyRow} onClose={() => setHistoryRow(null)} />
    </div>
  )
}

// ── 회차 스냅샷 이력 Modal — GET /settlements/{map_id}/snapshots (seq 오름차순) ──
function SnapshotHistoryModal({
  row,
  onClose,
}: {
  row: ProjectClientMap | null
  onClose: () => void
}) {
  const { data: snapshots = [], isLoading, isError } = useSettlementSnapshots(
    row?.map_id ?? null,
  )
  return (
    <Modal
      open={!!row}
      onClose={onClose}
      title="정산 회차 이력"
      size="lg"
      footer={
        <button
          type="button"
          onClick={onClose}
          className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
        >
          닫기
        </button>
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-bone">
          <b>{row?.client_name ?? '—'}</b> · {row?.project_name ?? '—'}
        </p>
        <p className="rounded-xl border border-hairline bg-elevate px-3 py-2 text-xs text-ash">
          청구 시점에 동결된 금액입니다 — 이후 단가 변경에 영향받지 않습니다.
        </p>

        {isLoading ? (
          <div className="flex justify-center py-8">
            <CircleNotch size={20} className="animate-spin text-slatey" />
          </div>
        ) : isError ? (
          <p className="py-6 text-center text-sm text-slatey">
            이력을 불러오지 못했습니다 — 잠시 후 다시 시도해 주세요.
          </p>
        ) : snapshots.length === 0 ? (
          <p className="py-6 text-center text-sm text-slatey">
            아직 회차 이력이 없습니다 — 청구서 발행 시점에 첫 회차가 동결됩니다.
          </p>
        ) : (
          <ul className="max-h-[45vh] space-y-2 overflow-y-auto">
            {snapshots.map((s) => {
              const action = SNAPSHOT_ACTIONS[s.action] ?? {
                label: s.action,
                className: 'bg-white/8 text-slate-600 dark:text-slate-300 border-white/15',
              }
              return (
                <li key={s.snapshot_id} className="rounded-xl border border-hairline bg-elevate p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-bold text-bone">{s.seq}회차</span>
                    <span
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold ${action.className}`}
                    >
                      {action.label}
                    </span>
                    <span className="ml-auto text-xs text-slatey">
                      {fmtServerDateTime(s.created_at)}
                      {(s.created_by_name ?? s.created_by) && ` · ${s.created_by_name ?? s.created_by}`}
                    </span>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
                    <div>
                      <p className="text-xs text-ash">동결 금액</p>
                      {s.amount != null ? (
                        <SensitiveData type="money" value={fmtMoney(Number(s.amount))} />
                      ) : (
                        <span className="text-xs text-slatey">미정</span>
                      )}
                    </div>
                    <div>
                      <p className="text-xs text-ash">단가</p>
                      {s.unit_price != null ? (
                        <SensitiveData type="money" value={fmtMoney(Number(s.unit_price))} />
                      ) : (
                        <span className="text-xs text-slatey">—</span>
                      )}
                    </div>
                    <div>
                      <p className="text-xs text-ash">지분율 / 보수율</p>
                      <span className="text-bone">
                        {s.allocation_ratio != null ? `${Number(s.allocation_ratio)} %` : '—'}
                      </span>{' '}
                      <span className="text-slatey">/</span>{' '}
                      {s.success_fee_rate != null ? (
                        <SensitiveData type="rate" value={`${Number(s.success_fee_rate)} %`} />
                      ) : (
                        <span className="text-slatey">—</span>
                      )}
                    </div>
                    <div>
                      <p className="text-xs text-ash">입금액</p>
                      {s.paid_amount != null ? (
                        <SensitiveData type="money" value={fmtMoney(Number(s.paid_amount))} />
                      ) : (
                        <span className="text-xs text-slatey">—</span>
                      )}
                    </div>
                  </div>
                  {s.reason && <p className="mt-1.5 text-xs text-ash">사유: {s.reason}</p>}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </Modal>
  )
}
