// SCR-06 사업 상세 — 개요 + 진행 단계 + 참여 운수사·차량 + 회계 원장층
import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { fmt2, Num } from '../../components/Num'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  CaretLeft,
  CaretRight,
  Check,
  CircleNotch,
  DownloadSimple,
  MagnifyingGlass,
  PencilSimple,
  Plus,
  Trash,
  UploadSimple,
  X,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { StatusBadge } from '../../components/StatusBadge'
import { SensitiveData } from '../../components/SensitiveData'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { EmptyState } from '../../components/EmptyState'
import { Skeleton } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { useClientOptions, useCodes } from '../../lib/api/queries'
import { FINANCE_FEATURES } from '../../lib/featureFlags'
import { useDebounced } from '../../lib/useDebounced'
import { dday, fmtDate, fmtMoney, fmtServerDateTime } from '../../lib/format'
import type {
  Project,
  ProjectOperator,
  ProjectSale,
  ProjectVehicle,
  PurchaseInvoice,
} from '../../types'
import {
  downloadVehicleTemplate,
  isIssueImminent,
  useDeleteProject,
  useDeletePurchaseInvoice,
  useDeleteSale,
  useDeleteVehicle,
  useImportVehicles,
  useProject,
  useProjectOperators,
  useProjectVehicles,
  usePurchaseInvoices,
  useUpdateApprovalStatus,
  useUpdatePayoutParams,
  useUpdateStages,
} from './api'
import { ProjectFormModal } from './ProjectFormModal'
import { VehicleFormModal } from './VehicleFormModal'
import { SaleFormModal } from './SaleFormModal'
import { PurchaseInvoiceFormModal } from './PurchaseInvoiceFormModal'

function OverviewItem({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="text-[10px] font-semibold tracking-wider text-slatey uppercase">{label}</p>
      <div className="mt-1 text-sm text-bone">{children}</div>
    </div>
  )
}

/** 톤당 단가 인라인 편집 공용 — 미입력 "미정", 저장 시 successMsg 토스트 */
function InlinePriceEditor({
  value: current,
  pending,
  onSubmit,
  successMsg,
  ariaLabel,
  placeholder = '원/tCO₂',
}: {
  value?: number | string | null
  pending: boolean
  onSubmit: (v: number | null) => Promise<unknown>
  successMsg: string
  ariaLabel: string
  placeholder?: string
}) {
  const { showToast } = useToast()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')

  const startEdit = () => {
    setValue(current != null ? String(current) : '')
    setEditing(true)
  }

  const submit = async () => {
    try {
      await onSubmit(value === '' ? null : Number(value))
      showToast(successMsg, 'success')
      setEditing(false)
    } catch {
      showToast('단가 저장에 실패했습니다.', 'danger')
    }
  }

  if (editing) {
    return (
      <div className="flex items-center gap-1.5">
        <input
          type="number"
          min={0}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              submit()
            }
            if (e.key === 'Escape') setEditing(false)
          }}
          autoFocus
          className="h-8 w-32 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
          placeholder={placeholder}
          aria-label={ariaLabel}
        />
        <button
          type="button"
          onClick={submit}
          disabled={pending}
          className="rounded-md bg-primary p-1.5 text-on-primary hover:opacity-90 disabled:opacity-60"
          title="저장"
          aria-label="단가 저장"
        >
          {pending ? <CircleNotch size={14} className="animate-spin" /> : <Check size={14} weight="bold" />}
        </button>
        <button
          type="button"
          onClick={() => setEditing(false)}
          className="rounded-md border border-hairline p-1.5 text-ash hover:bg-elevate"
          title="취소"
          aria-label="편집 취소"
        >
          <X size={14} />
        </button>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-1.5">
      {current != null ? (
        <SensitiveData type="money" value={fmtMoney(Number(current))} />
      ) : (
        <span className="font-medium text-amber-400">미정</span>
      )}
      <button
        type="button"
        onClick={startEdit}
        className="rounded-md p-1 text-smoke hover:bg-elevate hover:text-bone"
        title="단가 수기 입력"
        aria-label={ariaLabel}
      >
        <PencilSimple size={14} />
      </button>
    </div>
  )
}

/** 최대지급액(차량당 상한) — PUT /projects/{id}/payout-params, 저장 시 전 차량 예상지급액 재계산 + 승인일 자동 */
function MaxPaymentEditor({ projectId, unitPrice }: { projectId: string; unitPrice?: number | string | null }) {
  const update = useUpdatePayoutParams(projectId)
  return (
    <InlinePriceEditor
      value={unitPrice}
      pending={update.isPending}
      onSubmit={(v) => update.mutateAsync({ max_payment: v })}
      successMsg="최대지급액이 저장되었습니다. 참여 차량 예상지급액이 재계산됩니다."
      ariaLabel="최대지급액"
      placeholder="원"
    />
  )
}

/** 승인일 인라인 편집 — PUT /projects/{id}/payout-params(approved_at), 잔여차령 산정 기준. 미승인 시 "미승인" 표기 */
function ApprovedAtEditor({ projectId, approvedAt }: { projectId: string; approvedAt?: string | null }) {
  const { showToast } = useToast()
  const update = useUpdatePayoutParams(projectId)
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')

  const startEdit = () => {
    setValue(approvedAt ? approvedAt.slice(0, 10) : '')
    setEditing(true)
  }

  const submit = async () => {
    try {
      await update.mutateAsync({ approved_at: value === '' ? null : value })
      showToast('승인일이 저장되었습니다. 참여 차량 예상지급액이 재계산됩니다.', 'success')
      setEditing(false)
    } catch {
      showToast('승인일 저장에 실패했습니다.', 'danger')
    }
  }

  if (editing) {
    return (
      <div className="flex items-center gap-1.5">
        <input
          type="date"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              submit()
            }
            if (e.key === 'Escape') setEditing(false)
          }}
          autoFocus
          className="h-8 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
          aria-label="승인일"
        />
        <button
          type="button"
          onClick={submit}
          disabled={update.isPending}
          className="rounded-md bg-primary p-1.5 text-on-primary hover:opacity-90 disabled:opacity-60"
          title="저장"
          aria-label="승인일 저장"
        >
          {update.isPending ? <CircleNotch size={14} className="animate-spin" /> : <Check size={14} weight="bold" />}
        </button>
        <button
          type="button"
          onClick={() => setEditing(false)}
          className="rounded-md border border-hairline p-1.5 text-ash hover:bg-elevate"
          title="취소"
          aria-label="편집 취소"
        >
          <X size={14} />
        </button>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-1.5">
      {approvedAt ? (
        <span className="text-bone">{fmtDate(approvedAt)}</span>
      ) : (
        <span className="font-medium text-amber-400">미승인</span>
      )}
      <button
        type="button"
        onClick={startEdit}
        className="rounded-md p-1 text-smoke hover:bg-elevate hover:text-bone"
        title="승인일 수기 입력"
        aria-label="승인일"
      >
        <PencilSimple size={14} />
      </button>
    </div>
  )
}

/** 승인상태 인라인 편집 — useCodes('APPROVAL_STATUS') 드롭다운, PUT /projects/{id}. 미입력 시 "미승인" 취급 */
function ApprovalStatusEditor({
  projectId,
  approvalStatus,
}: {
  projectId: string
  approvalStatus?: string | null
}) {
  const { showToast } = useToast()
  const { options, labelOf } = useCodes('APPROVAL_STATUS')
  const update = useUpdateApprovalStatus(projectId)
  const [editing, setEditing] = useState(false)

  const onChange = async (value: string) => {
    try {
      await update.mutateAsync(value || null)
      showToast('승인상태가 저장되었습니다.', 'success')
      setEditing(false)
    } catch {
      showToast('승인상태 저장에 실패했습니다.', 'danger')
    }
  }

  if (editing) {
    return (
      <select
        value={approvalStatus ?? ''}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => setEditing(false)}
        disabled={update.isPending}
        autoFocus
        className="h-8 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none disabled:opacity-60"
        aria-label="승인상태"
      >
        <option value="">미승인</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    )
  }

  return (
    <div className="flex items-center gap-1.5">
      {approvalStatus ? (
        <span className="text-bone">{labelOf(approvalStatus)}</span>
      ) : (
        <span className="font-medium text-amber-400">미승인</span>
      )}
      <button
        type="button"
        onClick={() => setEditing(true)}
        className="rounded-md p-1 text-smoke hover:bg-elevate hover:text-bone"
        title="승인상태 변경"
        aria-label="승인상태"
      >
        <PencilSimple size={14} />
      </button>
    </div>
  )
}

// 개요 카드 — 승인상태·승인일·최대지급액·톤당단가 인라인 편집 포함. dday/imminent 자체 산출.
function OverviewSection({
  project,
  primaryClientName,
}: {
  project: Project
  primaryClientName: string | null
}) {
  const dd = dday(project.expected_issue_date)
  const imminent = isIssueImminent(dd)

  return (
    <section className="rounded-3xl border border-hairline bg-graphite p-5">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <StatusBadge domain="project" value={project.project_status} />
        {project.reg_code && (
          <span className="inline-flex items-center rounded border border-hairline bg-elevate px-1.5 py-0.5 font-mono text-[10px] text-ash">
            {project.reg_code}
          </span>
        )}
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <OverviewItem label="대표 고객사">
          {project.client_id ? (
            <Link to={`/clients/${project.client_id}`} className="font-semibold hover:underline">
              {primaryClientName ?? '고객사 보기'}
            </Link>
          ) : (
            '—'
          )}
        </OverviewItem>
        <OverviewItem label="담당 PM">{project.manager_name ?? '—'}</OverviewItem>
        <OverviewItem label="유효기간">
          {project.credit_start_date || project.credit_end_date
            ? `${fmtDate(project.credit_start_date)} ~ ${fmtDate(project.credit_end_date)}`
            : '기간 미정'}
        </OverviewItem>
        <OverviewItem label="모니터링">
          {project.mon_start_date || project.mon_end_date
            ? `${fmtDate(project.mon_start_date)} ~ ${fmtDate(project.mon_end_date)}`
            : '기간 미정'}
          {project.mon_cycle ? ` (${project.mon_cycle})` : ''}
        </OverviewItem>
        <OverviewItem label="예상 발급일">
          {project.expected_issue_date ? (
            <span className="flex items-center gap-1.5">
              {fmtDate(project.expected_issue_date)}
              {dd && (
                <span
                  className={`text-xs font-bold ${imminent ? 'text-rose-400' : 'text-slatey'}`}
                >
                  {dd.label}
                </span>
              )}
            </span>
          ) : (
            '미정'
          )}
        </OverviewItem>
        <OverviewItem label="예상 발급량">
          {project.expected_credits != null ? (
            <SensitiveData
              type="text"
              value={`${fmt2(project.expected_credits)} tCO₂`}
            />
          ) : (
            '—'
          )}
        </OverviewItem>
        {project.issued_credits != null && (
          <OverviewItem label="확정 발급량">
            <SensitiveData
              type="text"
              value={`${fmt2(project.issued_credits)} tCO₂`}
            />
            {project.issued_at && (
              <span className="ml-1.5 text-xs text-slatey">({fmtDate(project.issued_at)})</span>
            )}
          </OverviewItem>
        )}
        <OverviewItem label="최대지급액 (차량당 상한)">
          <MaxPaymentEditor projectId={project.project_id} unitPrice={project.max_payment} />
        </OverviewItem>
        <OverviewItem label="승인일">
          <ApprovedAtEditor projectId={project.project_id} approvedAt={project.approved_at} />
        </OverviewItem>
        <OverviewItem label="승인상태">
          <ApprovalStatusEditor
            projectId={project.project_id}
            approvalStatus={project.approval_status}
          />
        </OverviewItem>
      </div>
      {/* 공동 관리 가시화 — 등록/수정 일시 (작성자 조인은 백엔드 미제공) */}
      <p className="mt-4 border-t border-hairline pt-3 text-xs text-slatey">
        {project.created_at && `등록 ${fmtServerDateTime(project.created_at)}`}
        {project.updated_at && ` / 수정 ${fmtServerDateTime(project.updated_at)}`}
      </p>
    </section>
  )
}

type TabKey = 'overview' | 'vehicles' | 'finance'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'overview', label: '개요·진행' },
  { key: 'vehicles', label: '참여 차량' },
  { key: 'finance', label: '재무' },
]

/** 재무 플래그에 따른 표시 탭(순수). OFF면 finance 탭 제거, ON이면 원본 그대로. */
export function visibleProjectTabs(financeEnabled: boolean): { key: TabKey; label: string }[] {
  return financeEnabled ? TABS : TABS.filter((t) => t.key !== 'finance')
}

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { showToast } = useToast()

  const { data: project, isLoading, isError } = useProject(projectId)
  const { data: clientOptions = [] } = useClientOptions()
  const deleteProject = useDeleteProject()
  const navigate = useNavigate()

  const [tab, setTab] = useState<TabKey>('overview')
  const [editOpen, setEditOpen] = useState(false)
  const [deleteProjectOpen, setDeleteProjectOpen] = useState(false)

  // 대표 고객사명 — ProjectOut에 client_name 미포함 → 옵션 목록에서 조회
  const primaryClientName = useMemo(
    () => clientOptions.find((c) => c.client_id === project?.client_id)?.company_name ?? null,
    [clientOptions, project],
  )

  if (isLoading) {
    return (
      <div className="animate-fade-in space-y-4">
        <Skeleton className="h-8 w-64" />
        <div className="rounded-3xl border border-hairline bg-graphite p-5">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="mt-3 h-3 w-full" />
          <Skeleton className="mt-2 h-3 w-2/3" />
        </div>
      </div>
    )
  }

  if (isError || !project) {
    return (
      <EmptyState
        title="사업 정보를 불러오지 못했습니다"
        description="주소를 확인하거나 목록에서 다시 진입해 주세요."
        action={
          <Link
            to="/projects"
            className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
          >
            목록으로
          </Link>
        }
      />
    )
  }

  return (
    <div className="animate-fade-in space-y-4">
      <Link
        to="/projects"
        className="inline-flex items-center gap-1 text-sm text-slatey hover:text-ash"
      >
        <ArrowLeft size={14} />
        감축 사업 목록
      </Link>

      <PageHeader
        title={project.project_name}
        subtitle={project.reg_code ?? undefined}
        actions={
          /* 수정·삭제 — 모바일 숨김 (§7.1) */
          <div className="hidden items-center gap-2 sm:flex">
            <button
              type="button"
              onClick={() => setEditOpen(true)}
              className="flex items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate"
            >
              <PencilSimple size={15} />
              사업 수정
            </button>
            <button
              type="button"
              onClick={() => setDeleteProjectOpen(true)}
              className="flex items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-rose-400 hover:bg-rose-500/10"
            >
              <Trash size={15} />
              사업 삭제
            </button>
          </div>
        }
      />

      {/* 탭 — 재무 OFF면 finance 탭 제외 */}
      <div className="flex gap-1 overflow-x-auto border-b border-hairline">
        {visibleProjectTabs(FINANCE_FEATURES).map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`shrink-0 border-b-2 px-3.5 py-2.5 text-sm font-medium transition-colors ${
              tab === t.key
                ? 'border-snow text-bone'
                : 'border-transparent text-slatey hover:text-ash'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 개요·진행 */}
      {tab === 'overview' && (
        <>
          <OverviewSection project={project} primaryClientName={primaryClientName} />
          {/* 진행 단계 타임라인 (Phase 1) */}
          <StageTimeline project={project} />
        </>
      )}

      {/* 참여 차량 */}
      {tab === 'vehicles' && (
        <>
          {/* 참여 운수사 롤업 (운수사별 집계 + 행 펼침 차량 목록) */}
          <OperatorsSection projectId={project.project_id} />
          {/* 참여 차량 (Phase 2) */}
          <VehiclesSection projectId={project.project_id} />
        </>
      )}

      {/* 재무 — 재무 OFF면 탭 자체가 없어 진입 불가(방어적으로 플래그도 확인) */}
      {FINANCE_FEATURES && tab === 'finance' && (
        <>
          <div className="flex justify-end">
            <Link
              to="/finance-ledger"
              className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate"
            >
              전사 재무 원장 보기
            </Link>
          </div>
          {/* 매입세금계산서 (P·B 회계 원장층 — 총매입=제품 산출) */}
          <PurchaseInvoicesSection projectId={project.project_id} />
          {/* 거래계약 (매수자별 선물 판매단가) + 회계 요약 */}
          <SalesSection project={project} />
        </>
      )}

      <ProjectFormModal open={editOpen} onClose={() => setEditOpen(false)} project={project} />
      <ConfirmDialog
        open={deleteProjectOpen}
        title="사업 삭제"
        message={
          <>
            <b>{project.project_name}</b> 사업을 삭제합니다. 참여 고객사 매핑도 함께 제거되며, 이
            작업은 되돌릴 수 없습니다. (정산이 진행된 사업은 삭제되지 않습니다.)
          </>
        }
        confirmLabel="삭제"
        danger
        loading={deleteProject.isPending}
        onCancel={() => setDeleteProjectOpen(false)}
        onConfirm={async () => {
          if (!projectId) return
          try {
            await deleteProject.mutateAsync(projectId)
            showToast('사업이 삭제되었습니다.', 'success')
            setDeleteProjectOpen(false)
            navigate('/projects')
          } catch (err) {
            const detail = (err as { response?: { data?: { detail?: string } } })?.response
              ?.data?.detail
            showToast(detail || '삭제에 실패했습니다.', 'danger')
          }
        }}
      />
    </div>
  )
}

// 진행 단계 타임라인 (Phase 1) — 5단계 예정일 편집 + 실제일·지연 표시
function StageTimeline({ project }: { project: Project }) {
  const { labelOf } = useCodes('PROJECT_STATUS')
  const update = useUpdateStages(project.project_id)
  const { showToast } = useToast()
  const stages = useMemo(
    () => [...(project.stages ?? [])].sort((a, b) => (a.sort_order ?? 999) - (b.sort_order ?? 999)),
    [project.stages],
  )
  // 예정일 편집 드래프트 — 서버 데이터가 갱신되면 동기화
  const [draft, setDraft] = useState<Record<string, string>>({})
  useEffect(() => {
    setDraft(Object.fromEntries(stages.map((s) => [s.stage_code, s.planned_date ?? ''])))
  }, [stages])

  const dirty = stages.some((s) => (s.planned_date ?? '') !== (draft[s.stage_code] ?? ''))
  const delayedCount = stages.filter((s) => s.delayed).length

  const save = async () => {
    try {
      await update.mutateAsync(
        stages.map((s) => ({ stage_code: s.stage_code, planned_date: draft[s.stage_code] || null })),
      )
      showToast('진행 단계 예정일을 저장했습니다.', 'success')
    } catch {
      showToast('저장에 실패했습니다.', 'danger')
    }
  }

  return (
    <section className="rounded-3xl border border-hairline bg-graphite p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-bold text-bone">진행 단계</h2>
          {delayedCount > 0 && (
            <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-xs font-bold text-rose-700 dark:text-rose-300">
              지연 {delayedCount}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={save}
          disabled={!dirty || update.isPending}
          className="rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-on-primary hover:opacity-90 disabled:opacity-50"
        >
          {update.isPending ? '저장 중…' : '예정일 저장'}
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-sm">
          <thead>
            <tr className="border-b border-hairline text-xs text-slatey">
              <th className="px-2 py-2 text-left font-semibold">단계</th>
              <th className="px-2 py-2 text-left font-semibold">예정일</th>
              <th className="px-2 py-2 text-left font-semibold">실제일</th>
              <th className="px-2 py-2 text-left font-semibold">상태</th>
            </tr>
          </thead>
          <tbody>
            {stages.map((s) => (
              <tr key={s.stage_code} className="border-b border-hairline/60 last:border-b-0">
                <td className="px-2 py-2 font-medium text-bone">{labelOf(s.stage_code)}</td>
                <td className="px-2 py-2">
                  <input
                    type="date"
                    value={draft[s.stage_code] ?? ''}
                    onChange={(e) =>
                      setDraft((prev) => ({ ...prev, [s.stage_code]: e.target.value }))
                    }
                    className="rounded-md border border-hairline bg-graphite-2 px-2 py-1 text-xs text-bone focus:border-white/30 focus:outline-none"
                  />
                </td>
                <td className="px-2 py-2 text-ash">{s.actual_date ? fmtDate(s.actual_date) : '—'}</td>
                <td className="px-2 py-2">
                  {s.actual_date ? (
                    <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400">완료</span>
                  ) : s.delayed ? (
                    <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-xs font-bold text-rose-700 dark:text-rose-300">
                      지연
                    </span>
                  ) : (
                    <span className="text-xs text-slatey">대기</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-slatey">
        상태를 진행하면 해당 단계 실제일이 자동 기록됩니다. 예정일이 지났는데 미도달이면 지연으로 표시됩니다.
      </p>
    </section>
  )
}

// 참여 차량 (Phase 2) — 감축량·예상지급액 ingest. 목록 + 등록/수정/삭제
const VEHICLE_PAGE_SIZE = 50

// 참여 운수사 롤업 — 운수사별 집계 표, 행 펼침 시 해당 운수사 차량 인라인
function OperatorsSection({ projectId }: { projectId: string }) {
  const { data } = useProjectOperators(projectId)
  // 펼친 운수사 키(client_id, null은 '미지정' 키로 대체)
  const [expanded, setExpanded] = useState<string | null>(null)
  const operators = data?.items ?? []

  const keyOf = (o: ProjectOperator) => o.client_id ?? '__none__'

  return (
    <section className="space-y-3">
      <div className="flex items-baseline gap-3">
        <h2 className="text-base font-bold text-bone">참여 운수사</h2>
        {data && <span className="text-xs text-slatey">{data.total.toLocaleString()}곳</span>}
      </div>

      {operators.length === 0 ? (
        <EmptyState
          icon={<Plus size={28} />}
          title="참여 운수사가 없습니다"
          description="참여 차량을 등록하면 운수사별 집계가 표시됩니다."
          className="py-8"
        />
      ) : (
        <div className="overflow-x-auto rounded-3xl border border-hairline bg-graphite">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-hairline text-xs text-slatey">
                <th className="px-3 py-2.5 text-left font-semibold">운수사명</th>
                <th className="px-3 py-2.5 text-right font-semibold">차량수</th>
                <th className="px-3 py-2.5 text-right font-semibold">잔여반영감축량(tCO₂)</th>
                {FINANCE_FEATURES && (
                  <th className="px-3 py-2.5 text-right font-semibold">예상지급액</th>
                )}
              </tr>
            </thead>
            <tbody>
              {operators.map((o) => {
                const key = keyOf(o)
                const isOpen = expanded === key
                return (
                  <Fragment key={key}>
                    <tr
                      onClick={() => setExpanded(isOpen ? null : key)}
                      className="cursor-pointer border-b border-hairline/60 last:border-b-0 hover:bg-elevate"
                    >
                      <td className="px-3 py-2.5 font-medium text-bone">
                        <span className="flex items-center gap-1.5">
                          <CaretRight
                            size={13}
                            weight="bold"
                            className={`text-slatey transition-transform ${isOpen ? 'rotate-90' : ''}`}
                          />
                          {o.client_name ?? '미지정'}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-right text-ash">
                        {o.vehicle_count.toLocaleString()}대
                      </td>
                      <td className="px-3 py-2.5 text-right text-ash">
                        {o.total_reduction != null ? o.total_reduction.toLocaleString() : '—'}
                      </td>
                      {FINANCE_FEATURES && (
                        <td className="px-3 py-2.5 text-right">
                          {o.total_expected_payout != null ? (
                            <SensitiveData type="money" value={fmtMoney(o.total_expected_payout)} />
                          ) : (
                            <span className="text-slatey">미정</span>
                          )}
                        </td>
                      )}
                    </tr>
                    {isOpen && (
                      <tr>
                        <td colSpan={FINANCE_FEATURES ? 4 : 3} className="bg-elevate/50 px-3 py-2">
                          <OperatorVehicles
                            projectId={projectId}
                            clientId={o.client_id ?? '__none__'}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

// 펼친 운수사의 차량 목록 — 펼쳐질 때만 조회(최대 50대), 초과분은 안내
function OperatorVehicles({ projectId, clientId }: { projectId: string; clientId?: string }) {
  const { data, isLoading } = useProjectVehicles(projectId, { clientId, pageSize: 50 })
  const vehicles = data?.items ?? []

  if (isLoading) return <p className="py-2 text-xs text-slatey">불러오는 중…</p>
  if (vehicles.length === 0) return <p className="py-2 text-xs text-slatey">차량이 없습니다.</p>

  const overflow = (data?.total ?? 0) - vehicles.length

  return (
    <div className="space-y-1.5">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-slatey">
            <th className="px-2 py-1 text-left font-semibold">차량번호</th>
            <th className="px-2 py-1 text-left font-semibold">지역</th>
            <th className="px-2 py-1 text-right font-semibold">잔여반영감축량(tCO₂)</th>
            {FINANCE_FEATURES && (
              <th className="px-2 py-1 text-right font-semibold">예상지급액</th>
            )}
          </tr>
        </thead>
        <tbody>
          {vehicles.map((v) => (
            <tr key={v.vehicle_id} className="border-t border-hairline/40">
              <td className="px-2 py-1 font-medium text-bone">{v.vehicle_no ?? '—'}</td>
              <td className="px-2 py-1 text-ash">{v.region ?? '—'}</td>
              <td className="px-2 py-1 text-right text-ash">
                {v.effective_reduction != null ? v.effective_reduction.toLocaleString() : '—'}
              </td>
              {FINANCE_FEATURES && (
                <td className="px-2 py-1 text-right">
                  {v.expected_payout != null ? (
                    <SensitiveData type="money" value={fmtMoney(v.expected_payout)} />
                  ) : (
                    <span className="text-slatey">—</span>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {overflow > 0 && (
        <p className="px-2 text-[11px] text-slatey">
          외 {overflow.toLocaleString()}대 — 참여 차량 섹션에서 전체 보기
        </p>
      )}
    </div>
  )
}

function VehiclesSection({ projectId }: { projectId: string }) {
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [page, setPage] = useState(1)
  useEffect(() => {
    setPage(1) // 검색어 변경 시 첫 페이지로
  }, [debouncedSearch])
  const { data } = useProjectVehicles(projectId, {
    page,
    pageSize: VEHICLE_PAGE_SIZE,
    search: debouncedSearch,
  })
  // 삭제 등으로 총건수가 줄어 현재 페이지가 범위를 벗어나면 마지막 페이지로 클램프
  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil((data?.total ?? 0) / VEHICLE_PAGE_SIZE))
    if (page > maxPage) setPage(maxPage)
  }, [data?.total, page])
  const { labelOf } = useCodes('VEHICLE_INTRO')
  const del = useDeleteVehicle(projectId)
  const importVehicles = useImportVehicles(projectId)
  const { showToast } = useToast()
  const fileRef = useRef<HTMLInputElement>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<ProjectVehicle | null>(null)
  const [deleting, setDeleting] = useState<ProjectVehicle | null>(null)
  const vehicles = data?.items ?? []

  const downloadTemplate = async () => {
    try {
      await downloadVehicleTemplate(projectId)
    } catch {
      showToast('양식 다운로드에 실패했습니다.', 'danger')
    }
  }

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (fileRef.current) fileRef.current.value = '' // 같은 파일 재선택 허용
    if (!file) return
    try {
      const r = await importVehicles.mutateAsync(file)
      const tail = r.skipped > 0 ? ` · 건너뜀 ${r.skipped}건(오류 행)` : ''
      showToast(
        r.created > 0
          ? `${r.created}대 등록 완료${tail}.`
          : `등록된 차량이 없습니다${tail}. 양식·값을 확인해 주세요.`,
        r.created > 0 ? 'success' : 'info',
      )
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      showToast(detail || '엑셀 업로드에 실패했습니다.', 'danger')
    }
  }

  const openCreate = () => {
    setEditing(null)
    setFormOpen(true)
  }
  const openEdit = (v: ProjectVehicle) => {
    setEditing(v)
    setFormOpen(true)
  }
  const confirmDelete = async () => {
    if (!deleting) return
    try {
      await del.mutateAsync(deleting.vehicle_id)
      showToast('차량이 삭제되었습니다.', 'success')
      setDeleting(null)
    } catch {
      showToast('삭제에 실패했습니다.', 'danger')
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-baseline gap-3">
          <h2 className="text-base font-bold text-bone">참여 차량</h2>
          {data && (
            <span className="text-xs text-slatey">
              {debouncedSearch ? '검색 ' : ''}
              {data.total.toLocaleString()}대 · 총감축량 <Num value={data.total_reduction} unit="tCO₂" />
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 self-start">
          <button
            type="button"
            onClick={downloadTemplate}
            className="flex items-center gap-1.5 rounded-full border border-hairline px-3 py-2 text-sm font-medium text-bone hover:bg-elevate"
          >
            <DownloadSimple size={15} /> 양식
          </button>
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={importVehicles.isPending}
            className="flex items-center gap-1.5 rounded-full border border-hairline px-3 py-2 text-sm font-medium text-bone hover:bg-elevate disabled:opacity-50"
          >
            {importVehicles.isPending ? (
              <CircleNotch size={15} className="animate-spin" />
            ) : (
              <UploadSimple size={15} />
            )}
            엑셀 업로드
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx"
            onChange={onUpload}
            className="hidden"
          />
          <button
            type="button"
            onClick={openCreate}
            className="flex items-center gap-1.5 rounded-full bg-primary px-3.5 py-2 text-sm font-medium text-on-primary hover:opacity-90"
          >
            <Plus size={15} weight="bold" /> 차량 등록
          </button>
        </div>
      </div>

      {/* 검색(차량번호·운수사) */}
      <div className="relative w-full sm:max-w-xs">
        <MagnifyingGlass
          size={15}
          className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-slatey"
        />
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="차량번호·운수사 검색…"
          className="w-full rounded-md border border-hairline bg-graphite py-2 pr-3 pl-9 text-sm text-bone outline-none placeholder:text-slatey focus:border-white/30"
          aria-label="차량 검색"
        />
      </div>

      {vehicles.length === 0 ? (
        <EmptyState
          icon={<Plus size={28} />}
          title={debouncedSearch ? '검색 결과가 없습니다' : '참여 차량이 없습니다'}
          description={
            debouncedSearch
              ? '다른 검색어로 다시 시도해 보세요.'
              : '[차량 등록] 또는 [엑셀 업로드]로 도입구분·연차 감축량을 입력하세요.'
          }
          className="py-8"
        />
      ) : (
        <div className="overflow-x-auto rounded-3xl border border-hairline bg-graphite">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-hairline text-xs text-slatey">
                <th className="px-3 py-2.5 text-left font-semibold">차량번호</th>
                <th className="px-3 py-2.5 text-left font-semibold">운수사</th>
                <th className="px-3 py-2.5 text-left font-semibold">도입구분</th>
                <th className="px-3 py-2.5 text-right font-semibold">총감축량(tCO₂)</th>
                <th className="px-3 py-2.5 text-right font-semibold">잔여반영감축량(tCO₂)</th>
                {FINANCE_FEATURES && (
                  <th className="px-3 py-2.5 text-right font-semibold">예상지급액</th>
                )}
                <th className="px-3 py-2.5 text-right font-semibold">관리</th>
              </tr>
            </thead>
            <tbody>
              {vehicles.map((v) => (
                <tr key={v.vehicle_id} className="border-b border-hairline/60 last:border-b-0">
                  <td className="px-3 py-2.5 font-medium text-bone">{v.vehicle_no ?? '—'}</td>
                  <td className="px-3 py-2.5 text-ash">{v.client_name ?? '—'}</td>
                  <td className="px-3 py-2.5 text-ash">
                    {v.introduction_type ? labelOf(v.introduction_type) : '—'}
                  </td>
                  <td className="px-3 py-2.5 text-right text-ash">
                    {v.total_reduction != null ? v.total_reduction.toLocaleString() : '—'}
                  </td>
                  <td className="px-3 py-2.5 text-right text-ash">
                    {v.effective_reduction != null ? v.effective_reduction.toLocaleString() : '—'}
                  </td>
                  {FINANCE_FEATURES && (
                    <td className="px-3 py-2.5 text-right">
                      {v.expected_payout != null ? (
                        <SensitiveData type="money" value={fmtMoney(v.expected_payout)} />
                      ) : (
                        <span className="text-slatey">—</span>
                      )}
                    </td>
                  )}
                  <td className="px-3 py-2.5">
                    <div className="flex justify-end gap-1">
                      <button
                        type="button"
                        onClick={() => openEdit(v)}
                        className="rounded-md p-1.5 text-smoke hover:bg-elevate hover:text-bone"
                        aria-label="차량 수정"
                      >
                        <PencilSimple size={15} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setDeleting(v)}
                        className="rounded-md p-1.5 text-smoke hover:bg-elevate hover:text-rose-400"
                        aria-label="차량 삭제"
                      >
                        <Trash size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 페이지네이션 */}
      {(data?.total ?? 0) > VEHICLE_PAGE_SIZE && (
        <div className="flex items-center justify-between text-xs text-slatey">
          <span>
            {(page - 1) * VEHICLE_PAGE_SIZE + 1}–{(page - 1) * VEHICLE_PAGE_SIZE + vehicles.length} /
            총 {data?.total.toLocaleString()}대
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="rounded-md border border-hairline p-1.5 text-bone hover:bg-elevate disabled:opacity-40"
              aria-label="이전 페이지"
            >
              <CaretLeft size={14} />
            </button>
            <span className="px-1">
              {page} / {Math.max(1, Math.ceil((data?.total ?? 0) / VEHICLE_PAGE_SIZE))}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => p + 1)}
              disabled={page >= Math.ceil((data?.total ?? 0) / VEHICLE_PAGE_SIZE)}
              className="rounded-md border border-hairline p-1.5 text-bone hover:bg-elevate disabled:opacity-40"
              aria-label="다음 페이지"
            >
              <CaretRight size={14} />
            </button>
          </div>
        </div>
      )}

      <VehicleFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        projectId={projectId}
        vehicle={editing}
      />
      <ConfirmDialog
        open={!!deleting}
        title="차량 삭제"
        message={`${deleting?.vehicle_no ?? '해당 차량'}을(를) 삭제합니다.`}
        confirmLabel="삭제"
        danger
        loading={del.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={confirmDelete}
      />
    </section>
  )
}

// 회계 요약 (P·B 회계 원장층) — 예상지급액·제품(매입)·미착품·부채·재고자산·지급률·매출인식·매출이익·이익률.
// 내부 전용, 서버 파생값(단가·파라미터 게이트). null이면 "산출 대기". 금액은 SensitiveData로 마스킹.
function MarginSummary({ project }: { project: Project }) {
  const has =
    project.sale_amount != null ||
    project.payout_amount != null ||
    project.margin_amount != null ||
    project.product != null ||
    project.sale_recognized != null
  const money = (v?: number | null) =>
    v != null ? (
      <SensitiveData type="money" value={fmtMoney(Number(v))} />
    ) : (
      <span className="text-xs font-medium text-amber-400">산출 대기</span>
    )
  // 지급률·이익률은 0~1 비율 → % 표기, SensitiveData rate 마스킹
  const ratePct = (v?: number | null) =>
    v != null ? (
      <SensitiveData type="rate" value={`${(Number(v) * 100).toFixed(1)} %`} />
    ) : (
      <span className="text-xs font-medium text-amber-400">산출 대기</span>
    )
  return (
    <div className="rounded-3xl border border-hairline bg-graphite p-4">
      <div className="mb-3 flex items-center gap-2">
        <h3 className="text-sm font-bold text-bone">회계 요약</h3>
        <span className="rounded-full border border-amber-400/25 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300">
          내부 전용
        </span>
      </div>
      <div className="grid gap-4 sm:grid-cols-4">
        <OverviewItem label="예상지급액">{money(project.expected_payment)}</OverviewItem>
        <OverviewItem label="제품 (총매입)">{money(project.product)}</OverviewItem>
        <OverviewItem label="미착품1">{money(project.wip1)}</OverviewItem>
        <OverviewItem label="미착품2">{money(project.wip2)}</OverviewItem>
        <OverviewItem label="부채">{money(project.liability)}</OverviewItem>
        <OverviewItem label="재고자산">{money(project.inventory)}</OverviewItem>
        <OverviewItem label="지급률">{ratePct(project.payout_rate)}</OverviewItem>
        <OverviewItem label="매출인식">{money(project.sale_recognized)}</OverviewItem>
        <OverviewItem label="매출이익">{money(project.gross_profit)}</OverviewItem>
        <OverviewItem label="이익률">{ratePct(project.profit_rate)}</OverviewItem>
      </div>
      {/* 재고평가 (현재시세 기준, 비영속 read-only) — 후시보유분 × 현재 매출단가 시세.
          저장하지 않는 참조성 파생값이라 회계 원장(매출인식 등)과 분리해 표기한다. */}
      <div className="mt-3 grid gap-4 border-t border-hairline pt-3 sm:grid-cols-2">
        <OverviewItem label="현재시세 (원/tCO2)">
          {money(project.current_market_rate)}
        </OverviewItem>
        <OverviewItem label="재고평가 (현재시세 기준)">
          {project.inventory_valuation != null ? (
            money(project.inventory_valuation)
          ) : (
            <span className="text-xs font-medium text-slatey">
              후시보유·시세 입력 시 산출
            </span>
          )}
        </OverviewItem>
        {/* 예상수익 (비영속 read-only, B2) — Σ잔여반영감축량 × 직전 6개월 평균시세. */}
        <OverviewItem label="예상수익 (6개월 평균시세 기준)">
          {project.expected_revenue != null ? (
            money(project.expected_revenue)
          ) : (
            <span className="text-xs font-medium text-slatey">시세 입력 시 산출</span>
          )}
        </OverviewItem>
        <OverviewItem label="직전 6개월 평균시세 (원/tCO2)">
          {money(project.market_rate_avg6)}
        </OverviewItem>
      </div>
      {!has && (
        <p className="mt-3 text-xs text-slatey">
          매입세금계산서·거래계약(매출세금계산서)·단가·지급 파라미터가 입력되면 회계 항목이 자동
          산출됩니다.
        </p>
      )}
    </div>
  )
}

// 매입세금계산서 (P·B 회계 원장층) — 운수사·발행일·금액 목록 + 총액. 등록/수정/삭제(페이지네이션 없음).
function PurchaseInvoicesSection({ projectId }: { projectId: string }) {
  const { data } = usePurchaseInvoices(projectId)
  const del = useDeletePurchaseInvoice(projectId)
  const { showToast } = useToast()
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<PurchaseInvoice | null>(null)
  const [deleting, setDeleting] = useState<PurchaseInvoice | null>(null)
  const invoices = data?.items ?? []

  const openCreate = () => {
    setEditing(null)
    setFormOpen(true)
  }
  const openEdit = (i: PurchaseInvoice) => {
    setEditing(i)
    setFormOpen(true)
  }
  const confirmDelete = async () => {
    if (!deleting) return
    try {
      await del.mutateAsync(deleting.invoice_id)
      showToast('매입세금계산서가 삭제되었습니다.', 'success')
      setDeleting(null)
    } catch {
      showToast('삭제에 실패했습니다.', 'danger')
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-baseline gap-3">
          <h2 className="text-base font-bold text-bone">매입세금계산서</h2>
          {data && (
            <span className="text-xs text-slatey">
              {invoices.length.toLocaleString()}건 · 총매입{' '}
              <SensitiveData type="money" value={fmtMoney(Number(data.total_amount))} />
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="flex items-center gap-1.5 self-start rounded-full bg-primary px-3.5 py-2 text-sm font-medium text-on-primary hover:opacity-90"
        >
          <Plus size={15} weight="bold" /> 매입세금계산서 추가
        </button>
      </div>

      {invoices.length === 0 ? (
        <EmptyState
          icon={<Plus size={28} />}
          title="매입세금계산서가 없습니다"
          description="[매입세금계산서 추가]로 운수사·발행일·금액을 입력하세요."
          className="py-8"
        />
      ) : (
        <div className="overflow-x-auto rounded-3xl border border-hairline bg-graphite">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="border-b border-hairline text-xs text-slatey">
                <th className="px-3 py-2.5 text-left font-semibold">운수사</th>
                <th className="px-3 py-2.5 text-left font-semibold">지역</th>
                <th className="px-3 py-2.5 text-left font-semibold">발행일</th>
                <th className="px-3 py-2.5 text-right font-semibold">금액</th>
                <th className="px-3 py-2.5 text-right font-semibold">관리</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((i) => (
                <tr key={i.invoice_id} className="border-b border-hairline/60 last:border-b-0">
                  <td className="px-3 py-2.5 font-medium text-bone">
                    {i.operator_name ?? i.client_name ?? '—'}
                  </td>
                  <td className="px-3 py-2.5 text-ash">{i.region ?? '—'}</td>
                  <td className="px-3 py-2.5 text-ash">{i.issue_date ? fmtDate(i.issue_date) : '—'}</td>
                  <td className="px-3 py-2.5 text-right">
                    <SensitiveData type="money" value={fmtMoney(Number(i.amount))} />
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex justify-end gap-1">
                      <button
                        type="button"
                        onClick={() => openEdit(i)}
                        className="rounded-md p-1.5 text-smoke hover:bg-elevate hover:text-bone"
                        aria-label="매입세금계산서 수정"
                      >
                        <PencilSimple size={15} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setDeleting(i)}
                        className="rounded-md p-1.5 text-smoke hover:bg-elevate hover:text-rose-400"
                        aria-label="매입세금계산서 삭제"
                      >
                        <Trash size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <PurchaseInvoiceFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        projectId={projectId}
        invoice={editing}
      />
      <ConfirmDialog
        open={!!deleting}
        title="매입세금계산서 삭제"
        message={`${deleting?.operator_name ?? '해당'} 매입세금계산서를 삭제합니다.`}
        confirmLabel="삭제"
        danger
        loading={del.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={confirmDelete}
      />
    </section>
  )
}

// 거래계약 (매수자별 선물 판매단가) — 목록 + 등록/수정/삭제. 상세 응답 project.sales 사용(페이지네이션 없음).
function SalesSection({ project }: { project: Project }) {
  const projectId = project.project_id
  const { labelOf } = useCodes('SALE_BUYER_TYPE')
  const del = useDeleteSale(projectId)
  const { showToast } = useToast()
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<ProjectSale | null>(null)
  const [deleting, setDeleting] = useState<ProjectSale | null>(null)
  const sales = project.sales ?? []

  const openCreate = () => {
    setEditing(null)
    setFormOpen(true)
  }
  const openEdit = (s: ProjectSale) => {
    setEditing(s)
    setFormOpen(true)
  }
  const confirmDelete = async () => {
    if (!deleting) return
    try {
      await del.mutateAsync(deleting.sale_id)
      showToast('거래계약이 삭제되었습니다.', 'success')
      setDeleting(null)
    } catch {
      showToast('삭제에 실패했습니다.', 'danger')
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-baseline gap-3">
          <h2 className="text-base font-bold text-bone">거래계약 (매수자별 선물 판매단가)</h2>
          <span className="text-xs text-slatey">{sales.length.toLocaleString()}건</span>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="flex items-center gap-1.5 self-start rounded-full bg-primary px-3.5 py-2 text-sm font-medium text-on-primary hover:opacity-90"
        >
          <Plus size={15} weight="bold" /> 거래계약 추가
        </button>
      </div>

      <MarginSummary project={project} />

      {sales.length === 0 ? (
        <EmptyState
          icon={<Plus size={28} />}
          title="거래계약이 없습니다"
          description="[거래계약 추가]로 매수자별 선물 판매단가를 입력하세요."
          className="py-8"
        />
      ) : (
        <div className="overflow-x-auto rounded-3xl border border-hairline bg-graphite">
          <table className="w-full min-w-[860px] text-sm">
            <thead>
              <tr className="border-b border-hairline text-xs text-slatey">
                <th className="px-3 py-2.5 text-left font-semibold">매수자</th>
                <th className="px-3 py-2.5 text-left font-semibold">구분</th>
                <th className="px-3 py-2.5 text-right font-semibold">선물단가</th>
                <th className="px-3 py-2.5 text-right font-semibold">수량(tCO₂)</th>
                <th className="px-3 py-2.5 text-right font-semibold">금액</th>
                <th className="px-3 py-2.5 text-right font-semibold">실발행액</th>
                <th className="px-3 py-2.5 text-right font-semibold">소유권비율</th>
                <th className="px-3 py-2.5 text-center font-semibold">후시보유</th>
                <th className="px-3 py-2.5 text-left font-semibold">계약일</th>
                <th className="px-3 py-2.5 text-right font-semibold">관리</th>
              </tr>
            </thead>
            <tbody>
              {sales.map((s) => {
                const amount =
                  s.sale_unit_price != null && s.quantity != null
                    ? Number(s.sale_unit_price) * Number(s.quantity)
                    : null
                return (
                  <tr key={s.sale_id} className="border-b border-hairline/60 last:border-b-0">
                    <td className="px-3 py-2.5 font-medium text-bone">{s.buyer_name}</td>
                    <td className="px-3 py-2.5 text-ash">
                      {s.buyer_type ? labelOf(s.buyer_type) : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {s.sale_unit_price != null ? (
                        <SensitiveData type="money" value={fmtMoney(Number(s.sale_unit_price))} />
                      ) : (
                        <span className="text-slatey">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right text-ash">
                      {s.quantity != null ? Number(s.quantity).toLocaleString() : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {amount != null ? (
                        <SensitiveData type="money" value={fmtMoney(amount)} />
                      ) : (
                        <span className="text-slatey">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {s.sale_invoice_amount != null ? (
                        <SensitiveData type="money" value={fmtMoney(Number(s.sale_invoice_amount))} />
                      ) : (
                        <span className="text-slatey">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right text-ash">
                      {s.ownership_pct != null ? `${Number(s.ownership_pct)} %` : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      {s.is_hold === 'Y' ? (
                        <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-300">
                          후시보유
                        </span>
                      ) : (
                        <span className="text-slatey">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-ash">
                      {s.contract_date ? fmtDate(s.contract_date) : '—'}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => openEdit(s)}
                          className="rounded-md p-1.5 text-smoke hover:bg-elevate hover:text-bone"
                          aria-label="거래계약 수정"
                        >
                          <PencilSimple size={15} />
                        </button>
                        <button
                          type="button"
                          onClick={() => setDeleting(s)}
                          className="rounded-md p-1.5 text-smoke hover:bg-elevate hover:text-rose-400"
                          aria-label="거래계약 삭제"
                        >
                          <Trash size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <SaleFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        projectId={projectId}
        sale={editing}
      />
      <ConfirmDialog
        open={!!deleting}
        title="거래계약 삭제"
        message={`${deleting?.buyer_name ?? '해당'} 거래계약을 삭제합니다.`}
        confirmLabel="삭제"
        danger
        loading={del.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={confirmDelete}
      />
    </section>
  )
}
