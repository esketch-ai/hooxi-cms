// P4 정산 관리(SCR-07) — 정산 헤더 상태전이·스냅샷 이력 + 파이프라인 현황판(내부 탭).
// 내부 전용(OBSERVER·외부역할 제외 — nav roles + 백엔드 403). 전이는 settlement.change(MANAGER↑),
// 청구취소(BILLED→CONFIRMED)만 ADMIN 전용. 예정→확정은 [정산 확정] 진입점으로 생성한다.
import { type ReactNode, useMemo, useState } from 'react'
import { SectionTabs } from '../../components/SectionTabs'
import {
  ArrowUUpLeft,
  CheckCircle,
  CircleNotch,
  Coins,
  FlagCheckered,
  ListChecks,
  Receipt,
  Stack,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { ScreenGuide } from '../../components/ScreenGuide'
import { FilterBar, FilterSelect } from '../../components/FilterBar'
import { DataTable, type Column } from '../../components/DataTable'
import { KpiCard } from '../../components/KpiCard'
import { SensitiveData } from '../../components/SensitiveData'
import { StatusBadge } from '../../components/StatusBadge'
import { EmptyState } from '../../components/EmptyState'
import { Modal } from '../../components/Modal'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { RoleGate } from '../../components/RoleGate'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import { useCodes, useClientOptions, useUserOptions } from '../../lib/api/queries'
import { makeClientLabel } from '../../lib/clientLabel'
import { useProjectOptions } from '../projects/api'
import { fmtDateTime, fmtMoney } from '../../lib/format'
import {
  useConfirmSettlement,
  usePipeline,
  useSettlements,
  useSettlementSnapshots,
  useUpdateSettlementStatus,
} from './api'
import type { PipelineRow, SettlementOut, SettlementStatus } from './types'

/** 정수(차량수·감축량 등) 포맷 — nullable */
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

type Tab = 'list' | 'pipeline'

export function SettlementsPage() {
  const [tab, setTab] = useState<Tab>('list')

  return (
    <div className="animate-fade-in space-y-4">
      {/* 허브 서브탭(A안) — 재무/자산 묶음 화면 전환 */}
      <SectionTabs />
      <PageHeader
        title="정산 관리"
        subtitle="정산 헤더 상태전이·이력 + 부서 워크플로우 파이프라인 — 내부 전용"
      />

      <ScreenGuide
        perspective="정산 단위(운수사×사업)"
        links={[{ label: '예정 요약으로', to: '/asset-report' }]}
      >
        정산을 <strong className="font-medium text-bone">확정 → 청구 → 입금완료</strong>로 진행합니다.
        파이프라인 탭에서 수집 → 결산 → 정산 → 보고 → 통지 전체 단계를 봅니다.
      </ScreenGuide>

      {/* 탭 — 정산 목록 / 파이프라인 현황(과설계 회피: nav는 하나, 내부 탭으로 분리) */}
      <div className="flex gap-1.5 border-b border-hairline">
        <TabButton active={tab === 'list'} onClick={() => setTab('list')} icon={<ListChecks size={16} />}>
          정산 목록
        </TabButton>
        <TabButton active={tab === 'pipeline'} onClick={() => setTab('pipeline')} icon={<Stack size={16} />}>
          파이프라인 현황
        </TabButton>
      </div>

      {tab === 'list' ? <SettlementsListTab /> : <PipelineTab />}
    </div>
  )
}

function TabButton({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean
  onClick: () => void
  icon: ReactNode
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`-mb-px inline-flex items-center gap-1.5 border-b-2 px-3.5 py-2 text-sm font-medium transition ${
        active
          ? 'border-primary text-bone'
          : 'border-transparent text-slatey hover:text-bone'
      }`}
    >
      {icon}
      {children}
    </button>
  )
}

// ── 정산 목록 탭 ───────────────────────────────────────────────────────────
function SettlementsListTab() {
  const { user } = useAuth()
  // settlement.change(MANAGER↑) 없는 STAFF는 조회만(전이·확정 버튼 미노출). OBSERVER는 이 화면 접근 불가.
  const isManagerUp = user?.role === 'ADMIN' || user?.role === 'MANAGER'
  const isAdmin = user?.role === 'ADMIN'

  const { data: clients = [] } = useClientOptions()
  const { data: projects = [] } = useProjectOptions()
  const { options: statusOptions, labelOf: statusLabel } = useCodes('SETTLEMENT_STATUS')
  const { labelOf: clientTypeLabel } = useCodes('CLIENT_TYPE')
  const { data: users = [] } = useUserOptions()
  const userName = useMemo(() => {
    const m: Record<string, string> = {}
    for (const u of users) m[u.user_id] = u.name
    return (id?: string | null) => (id ? m[id] ?? '' : '')
  }, [users])

  const clientName = useMemo(() => {
    const m: Record<string, string> = {}
    for (const c of clients) m[c.client_id] = makeClientLabel(clientTypeLabel)(c)
    return (id: string) => m[id] ?? id
  }, [clients])
  const projectName = useMemo(() => {
    const m: Record<string, string> = {}
    for (const p of projects) m[p.project_id] = p.project_name
    return (id: string) => m[id] ?? id
  }, [projects])

  const [clientId, setClientId] = useState('')
  const [projectId, setProjectId] = useState('')
  const [status, setStatus] = useState('')
  const [expandedId, setExpandedId] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)

  const filters = useMemo(
    () => ({ client_id: clientId, project_id: projectId, status }),
    [clientId, projectId, status],
  )
  const { data, isLoading, isError, refetch } = useSettlements(filters)
  const rows = data?.items ?? []
  const total = data?.total ?? 0

  const columns: Column<SettlementOut>[] = [
    {
      key: 'client',
      header: '운수사',
      className: 'min-w-[160px]',
      render: (v) => <span className="font-semibold text-bone">{clientName(v.client_id)}</span>,
    },
    {
      key: 'project',
      header: '사업',
      className: 'min-w-[160px]',
      render: (v) => <span className="text-sm text-ash">{projectName(v.project_id)}</span>,
    },
    {
      key: 'period',
      header: '기간',
      render: (v) => <span className="text-sm text-ash">{v.period ?? '단일'}</span>,
    },
    {
      key: 'status',
      header: '상태',
      render: (v) => <StatusBadge domain="settlement" value={v.status} />,
    },
    {
      key: 'confirmed_amount',
      header: '확정액',
      className: 'text-right',
      render: (v) => <MoneyCell value={v.confirmed_amount} />,
    },
    {
      key: 'vehicle_count',
      header: '차량수',
      className: 'text-right',
      render: (v) => <span className="text-sm text-bone">{fmtQty(v.vehicle_count)}</span>,
    },
    {
      key: 'confirmed_at',
      header: '확정일',
      render: (v) => <span className="text-sm text-ash">{v.confirmed_at ? fmtDateTime(v.confirmed_at) : '—'}</span>,
    },
    {
      key: 'actions',
      header: '상태 전이',
      className: 'min-w-[220px]',
      render: (v) =>
        isManagerUp ? (
          <StatusTransition row={v} isAdmin={isAdmin} />
        ) : (
          <span className="text-xs text-slatey">조회 전용</span>
        ),
    },
  ]

  return (
    <div className="space-y-4">
      <FilterBar>
        <FilterSelect
          label="운수사"
          value={clientId}
          onChange={setClientId}
          options={clients.map((c) => ({ value: c.client_id, label: makeClientLabel(clientTypeLabel)(c) }))}
        />
        <FilterSelect
          label="사업"
          value={projectId}
          onChange={setProjectId}
          options={projects.map((p) => ({ value: p.project_id, label: p.project_name }))}
        />
        <FilterSelect label="상태" value={status} onChange={setStatus} options={statusOptions} />
        <div className="ml-auto">
          {/* 예정→확정 진입점 — settlement.change(MANAGER↑)만 */}
          <RoleGate allow={isManagerUp} reason="정산 확정은 팀장 이상만 가능합니다.">
            <button
              type="button"
              onClick={() => setConfirmOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-on-primary hover:opacity-90"
            >
              <CheckCircle size={16} />
              정산 확정
            </button>
          </RoleGate>
        </div>
      </FilterBar>

      {isError ? (
        <EmptyState
          icon={<Coins size={36} />}
          title="정산 목록을 불러오지 못했습니다"
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
          rowKey={(v) => v.settlement_id}
          onRowClick={(v) =>
            setExpandedId((prev) => (prev === v.settlement_id ? '' : v.settlement_id))
          }
          expandedKey={expandedId}
          renderExpanded={(v) => (
            <SnapshotPanel settlementId={v.settlement_id} userName={userName} statusLabel={statusLabel} />
          )}
          isLoading={isLoading}
          emptyTitle="확정된 정산이 없습니다"
          emptyDescription="자산관리 보고에서 예정 정산을 확정하거나 [정산 확정]으로 생성하세요."
        />
      )}

      {total > 0 && <p className="px-1 text-xs text-slatey">총 {fmtQty(total)} 건</p>}

      {confirmOpen && (
        <ConfirmCreateModal
          clients={clients.map((c) => ({ value: c.client_id, label: makeClientLabel(clientTypeLabel)(c) }))}
          projects={projects.map((p) => ({ value: p.project_id, label: p.project_name }))}
          onClose={() => setConfirmOpen(false)}
        />
      )}
    </div>
  )
}

/** 상태 전이 액션 — 현재 상태별 허용 전이 버튼 + 확인 다이얼로그(정방향 불가역 안내).
 *  CONFIRMED→BILLED, BILLED→COMPLETED(MANAGER↑) / BILLED→CONFIRMED 청구취소(ADMIN, 사유 필수). */
function StatusTransition({ row, isAdmin }: { row: SettlementOut; isAdmin: boolean }) {
  const { showToast } = useToast()
  const mutation = useUpdateSettlementStatus()
  // 진행 중 전이 확인 다이얼로그 대상(target). null이면 닫힘.
  const [pending, setPending] = useState<SettlementStatus | null>(null)
  const [reason, setReason] = useState('')

  const isRevert = pending === 'CONFIRMED'

  async function handleConfirm() {
    if (!pending) return
    try {
      await mutation.mutateAsync({
        settlement_id: row.settlement_id,
        target_status: pending,
        reason: isRevert ? reason : undefined,
      })
      showToast('정산 상태를 변경했습니다.', 'success')
      setPending(null)
      setReason('')
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '상태 변경에 실패했습니다.', 'danger')
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
      {row.status === 'CONFIRMED' && (
        <TransitionButton onClick={() => setPending('BILLED')} icon={<Receipt size={13} />}>
          청구서 발행
        </TransitionButton>
      )}
      {row.status === 'BILLED' && (
        <>
          <TransitionButton onClick={() => setPending('COMPLETED')} icon={<FlagCheckered size={13} />}>
            입금완료 처리
          </TransitionButton>
          {/* 청구취소(BILLED→CONFIRMED)는 ADMIN 전용 — role ADMIN 아니면 버튼 미노출 */}
          {isAdmin && (
            <TransitionButton
              onClick={() => setPending('CONFIRMED')}
              icon={<ArrowUUpLeft size={13} />}
              variant="danger"
            >
              청구취소
            </TransitionButton>
          )}
        </>
      )}
      {row.status === 'COMPLETED' && <span className="text-xs text-slatey">완료(종단)</span>}

      <ConfirmDialog
        open={pending !== null}
        title={
          pending === 'BILLED'
            ? '청구서 발행'
            : pending === 'COMPLETED'
            ? '입금완료 처리'
            : '청구 취소'
        }
        message={
          isRevert ? (
            <div className="space-y-2">
              <p>
                청구 상태를 <b className="text-bone">확정(CONFIRMED)</b>으로 되돌립니다. 청구 흔적이
                제거되며, 이 역전이는 ADMIN만 가능합니다.
              </p>
              <input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="취소 사유(필수)"
                className="w-full rounded-xl border border-hairline bg-elevate px-3 py-2 text-sm text-bone placeholder:text-smoke"
              />
            </div>
          ) : (
            <p>
              정산 상태를{' '}
              <b className="text-bone">{pending === 'BILLED' ? '청구(BILLED)' : '입금완료(COMPLETED)'}</b>
              (으)로 변경합니다. 상태는 정방향으로만 진행되며 되돌릴 수 없습니다.
            </p>
          )
        }
        confirmLabel={isRevert ? '청구취소' : '변경'}
        danger={isRevert}
        loading={mutation.isPending}
        onConfirm={handleConfirm}
        onCancel={() => {
          setPending(null)
          setReason('')
        }}
      />
    </div>
  )
}

function TransitionButton({
  onClick,
  icon,
  variant = 'default',
  children,
}: {
  onClick: () => void
  icon: ReactNode
  variant?: 'default' | 'danger'
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition ${
        variant === 'danger'
          ? 'border-rose-400/30 text-rose-700 hover:bg-rose-500/10 dark:text-rose-300'
          : 'border-hairline text-bone hover:bg-elevate'
      }`}
    >
      {icon}
      {children}
    </button>
  )
}

/** 행 펼침 — 스냅샷 이력(append-only, seq·action·amount·reason·일시) */
function SnapshotPanel({
  settlementId,
  userName,
  statusLabel,
}: {
  settlementId: string
  userName: (id?: string | null) => string
  statusLabel: (code?: string | null) => string
}) {
  const { data, isLoading } = useSettlementSnapshots(settlementId)
  const items = data?.items ?? []

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-slatey">
        <CircleNotch size={16} className="animate-spin" />
        이력을 불러오는 중…
      </div>
    )
  }
  if (items.length === 0) {
    return <p className="text-sm text-slatey">스냅샷 이력이 없습니다.</p>
  }

  return (
    <div className="space-y-2 text-sm">
      <h4 className="text-xs font-semibold tracking-wide text-ash">정산 스냅샷 이력 (append-only)</h4>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse">
          <thead>
            <tr className="border-b border-hairline text-left text-xs text-slatey">
              <th className="py-1.5 pr-4 font-medium">회차</th>
              <th className="py-1.5 pr-4 font-medium">액션</th>
              <th className="py-1.5 pr-4 text-right font-medium">금액</th>
              <th className="py-1.5 pr-4 font-medium">사유</th>
              <th className="py-1.5 pr-4 font-medium">처리자</th>
              <th className="py-1.5 font-medium">일시</th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.snapshot_id} className="border-b border-hairline/60">
                <td className="py-1.5 pr-4 text-ash">#{s.seq}</td>
                <td className="py-1.5 pr-4 text-bone">{statusLabel(s.action) || s.action}</td>
                <td className="py-1.5 pr-4 text-right">
                  <MoneyCell value={s.paid_amount ?? s.amount} />
                </td>
                <td className="py-1.5 pr-4 text-ash">{s.reason ?? '—'}</td>
                <td className="py-1.5 pr-4 text-ash">{userName(s.created_by) || '—'}</td>
                <td className="py-1.5 text-ash">{s.created_at ? fmtDateTime(s.created_at) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** 정산 확정 모달 — (운수사×사업[×기간]) 선택 → confirm. 예상지급액 전건 미산정이면 백엔드 409. */
function ConfirmCreateModal({
  clients,
  projects,
  onClose,
}: {
  clients: { value: string; label: string }[]
  projects: { value: string; label: string }[]
  onClose: () => void
}) {
  const { showToast } = useToast()
  const confirm = useConfirmSettlement()
  const [clientId, setClientId] = useState('')
  const [projectId, setProjectId] = useState('')
  const [period, setPeriod] = useState('') // 'YYYY-MM' 선택(단일이면 공란)

  async function handleConfirm() {
    if (!clientId || !projectId) {
      showToast('운수사와 사업을 선택하세요.', 'danger')
      return
    }
    try {
      await confirm.mutateAsync({
        client_id: clientId,
        project_id: projectId,
        period: period.trim() || undefined,
      })
      showToast('정산을 확정했습니다.', 'success')
      onClose()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '정산 확정에 실패했습니다.', 'danger')
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="정산 확정"
      size="md"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
          >
            취소
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={confirm.isPending || !clientId || !projectId}
            className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-on-primary hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {confirm.isPending && <CircleNotch size={14} className="animate-spin" />}
            확정
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-ash">
          선택한 (운수사 × 사업) 예정 정산을 확정합니다. 확정 시점의 예상지급액·차량수·잔여감축량이
          동결되며, 이후 값이 바뀌어도 확정액은 불변입니다.
        </p>
        <label className="block space-y-1">
          <span className="text-xs font-medium text-ash">운수사</span>
          <select
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            className="h-9 w-full rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
          >
            <option value="">선택</option>
            {clients.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block space-y-1">
          <span className="text-xs font-medium text-ash">사업</span>
          <select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className="h-9 w-full rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
          >
            <option value="">선택</option>
            {projects.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block space-y-1">
          <span className="text-xs font-medium text-ash">기간(선택, 단일 정산이면 공란)</span>
          <input
            type="month"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="h-9 w-full rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
          />
        </label>
      </div>
    </Modal>
  )
}

// ── 파이프라인 현황 탭 ─────────────────────────────────────────────────────
/** 5단계 코드→한국어 라벨(수집·결산·정산·보고·통지). none은 '미착수' */
const STAGE_LABEL: Record<string, string> = {
  none: '미착수',
  collect: '수집',
  accounting: '결산',
  settlement: '정산',
  report: '보고',
  notice: '통지',
}
const STAGE_ORDER = ['none', 'collect', 'accounting', 'settlement', 'report', 'notice']
const STAGE_CLASS: Record<string, string> = {
  none: 'bg-elevate-strong text-ash border-hairline',
  collect: 'bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-400/25',
  accounting: 'bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-400/25',
  settlement: 'bg-purple-500/15 text-purple-700 dark:text-purple-300 border-purple-400/25',
  report: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-400/25',
  notice: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-400/25',
}

function StageBadge({ stage }: { stage: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${
        STAGE_CLASS[stage] ?? STAGE_CLASS.none
      }`}
    >
      {STAGE_LABEL[stage] ?? stage}
    </span>
  )
}

function PipelineTab() {
  const { data: clients = [] } = useClientOptions()
  const { data: projects = [] } = useProjectOptions()
  const { options: statusOptions } = useCodes('SETTLEMENT_STATUS')
  const { labelOf: clientTypeLabel } = useCodes('CLIENT_TYPE')

  const [clientId, setClientId] = useState('')
  const [projectId, setProjectId] = useState('')
  const [settlementStatus, setSettlementStatus] = useState('')

  const filters = useMemo(
    () => ({ client_id: clientId, project_id: projectId, settlement_status: settlementStatus }),
    [clientId, projectId, settlementStatus],
  )
  const { data, isLoading, isError, refetch } = usePipeline(filters)
  const rows = data?.items ?? []
  const total = data?.total ?? 0
  const stageCounts = data?.stage_counts ?? null

  const columns: Column<PipelineRow>[] = [
    {
      key: 'company_name',
      header: '운수사',
      className: 'min-w-[150px]',
      render: (v) => (
        <span className={`font-semibold ${v.client_id ? 'text-bone' : 'text-slatey'}`}>
          {v.company_name}
        </span>
      ),
    },
    {
      key: 'project_name',
      header: '사업',
      className: 'min-w-[150px]',
      render: (v) => <span className="text-sm text-ash">{v.project_name}</span>,
    },
    {
      key: 'vehicle_count',
      header: '차량수',
      className: 'text-right',
      render: (v) => <span className="text-sm text-bone">{fmtQty(v.vehicle_count)}</span>,
    },
    {
      key: 'stage',
      header: '진행 단계',
      render: (v) => <StageBadge stage={v.stage} />,
    },
    {
      key: 'settlement_status',
      header: '정산 상태',
      render: (v) =>
        v.settlement_status ? (
          <StatusBadge domain="settlement" value={v.settlement_status} />
        ) : (
          <span className="text-xs text-slatey">예정</span>
        ),
    },
    {
      key: 'next_action',
      header: '다음 할일',
      className: 'min-w-[200px]',
      render: (v) => <span className="text-sm text-ash">{v.next_action}</span>,
    },
  ]

  return (
    <div className="space-y-4">
      {/* 단계별 요약 — stage_counts 있으면 KPI로. 5단계 순서 고정 */}
      {stageCounts && (
        <div className="grid grid-cols-3 gap-3 lg:grid-cols-6">
          {STAGE_ORDER.map((s) => (
            <KpiCard
              key={s}
              title={STAGE_LABEL[s]}
              value={fmtQty(stageCounts[s] ?? 0)}
              sub="현재 단계 셀 수"
              icon={<Stack size={16} />}
              variant="dark"
            />
          ))}
        </div>
      )}

      <FilterBar>
        <FilterSelect
          label="운수사"
          value={clientId}
          onChange={setClientId}
          options={clients.map((c) => ({ value: c.client_id, label: makeClientLabel(clientTypeLabel)(c) }))}
        />
        <FilterSelect
          label="사업"
          value={projectId}
          onChange={setProjectId}
          options={projects.map((p) => ({ value: p.project_id, label: p.project_name }))}
        />
        <FilterSelect
          label="정산 상태"
          value={settlementStatus}
          onChange={setSettlementStatus}
          options={statusOptions}
        />
      </FilterBar>

      {isError ? (
        <EmptyState
          icon={<Stack size={36} />}
          title="파이프라인을 불러오지 못했습니다"
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
          rowKey={(v) => `${v.client_id ?? 'none'}:${v.project_id}`}
          isLoading={isLoading}
          emptyTitle="해당 조건의 파이프라인이 없습니다"
          emptyDescription="필터를 조정해 주세요."
        />
      )}

      {total > 0 && <p className="px-1 text-xs text-slatey">총 {fmtQty(total)} 개 셀</p>}
    </div>
  )
}
