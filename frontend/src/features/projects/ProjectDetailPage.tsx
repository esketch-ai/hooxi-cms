// SCR-06 사업 상세 — 개요(단가 수기 입력) + 참여 고객사 매핑 + 배분율 합계 게이지
import { useMemo, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Check,
  CircleNotch,
  PencilSimple,
  Plus,
  Trash,
  Warning,
  X,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { StatusBadge } from '../../components/StatusBadge'
import { SensitiveData } from '../../components/SensitiveData'
import { DataTable, type Column } from '../../components/DataTable'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { EmptyState } from '../../components/EmptyState'
import { Skeleton } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { useClientOptions } from '../../lib/api/queries'
import { dday, fmtDate, fmtMoney, fmtServerDateTime } from '../../lib/format'
import type { ProjectClientMap } from '../../types'
import { isIssueImminent, useDeleteMapping, useProject, useUpdateUnitPrice } from './api'
import { ProjectFormModal } from './ProjectFormModal'
import { MappingFormModal } from './MappingFormModal'

function OverviewItem({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="text-[10px] font-semibold tracking-wider text-slatey uppercase">{label}</p>
      <div className="mt-1 text-sm text-bone">{children}</div>
    </div>
  )
}

/** 배출권 단가 인라인 편집 — PUT /projects/{id}/unit-price, 미입력 "미정" (§10.3) */
function UnitPriceEditor({
  projectId,
  unitPrice,
}: {
  projectId: string
  unitPrice?: number | string | null
}) {
  const { showToast } = useToast()
  const update = useUpdateUnitPrice(projectId)
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')

  const startEdit = () => {
    setValue(unitPrice != null ? String(unitPrice) : '')
    setEditing(true)
  }

  const submit = async () => {
    try {
      await update.mutateAsync(value === '' ? null : Number(value))
      showToast('배출권 단가가 저장되었습니다. 예상 정산액이 재계산됩니다.', 'success')
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
          placeholder="원/tCO₂"
          aria-label="배출권 단가"
        />
        <button
          type="button"
          onClick={submit}
          disabled={update.isPending}
          className="rounded-md bg-primary p-1.5 text-on-primary hover:opacity-90 disabled:opacity-60"
          title="저장"
          aria-label="단가 저장"
        >
          {update.isPending ? (
            <CircleNotch size={14} className="animate-spin" />
          ) : (
            <Check size={14} weight="bold" />
          )}
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
      {unitPrice != null ? (
        <SensitiveData type="money" value={fmtMoney(Number(unitPrice))} />
      ) : (
        <span className="font-medium text-amber-400">미정</span>
      )}
      <button
        type="button"
        onClick={startEdit}
        className="rounded-md p-1 text-smoke hover:bg-elevate hover:text-bone"
        title="단가 수기 입력"
        aria-label="단가 수기 입력"
      >
        <PencilSimple size={14} />
      </button>
    </div>
  )
}

/** 배분율 합계 게이지 — 100% 초과 시 빨강 경고 (SCR-06 §4.2) */
function AllocationGauge({ sum }: { sum: number }) {
  const over = sum > 100
  return (
    <div className="flex-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-ash">배분율 합계</span>
        <span className={`font-bold ${over ? 'text-rose-400' : 'text-bone'}`}>
          {sum.toFixed(1)}% / 100%
        </span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-elevate">
        <div
          className={`h-full rounded-full transition-all ${over ? 'bg-rose-500' : 'bg-primary'}`}
          style={{ width: `${Math.min(sum, 100)}%` }}
        />
      </div>
      {over && (
        <p className="mt-1.5 flex items-center gap-1 text-xs font-medium text-rose-400">
          <Warning size={13} weight="fill" />
          배분율 합계가 100%를 초과했습니다. 매핑을 조정해 주세요.
        </p>
      )}
    </div>
  )
}

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { showToast } = useToast()

  const { data: project, isLoading, isError } = useProject(projectId)
  // 매핑은 상세 응답(ProjectDetailOut.clients)에 포함 — routers/projects.py
  const mappings = useMemo(() => project?.clients ?? [], [project])
  const { data: clientOptions = [] } = useClientOptions()
  const deleteMapping = useDeleteMapping(projectId)

  const [editOpen, setEditOpen] = useState(false)
  const [mappingOpen, setMappingOpen] = useState(false)
  const [editingMapping, setEditingMapping] = useState<ProjectClientMap | null>(null)
  const [deleting, setDeleting] = useState<ProjectClientMap | null>(null)

  // 배분율 합계 — 서버 집계(allocation_total) 우선, 없으면 클라이언트 합산
  const allocationSum = useMemo(
    () =>
      project?.allocation_total ??
      mappings.reduce((acc, m) => acc + (Number(m.allocation_ratio) || 0), 0),
    [project, mappings],
  )

  // 대표 고객사명 — ProjectOut에 client_name 미포함 → 옵션 목록에서 조회
  const primaryClientName = useMemo(
    () => clientOptions.find((c) => c.client_id === project?.client_id)?.company_name ?? null,
    [clientOptions, project],
  )

  const dd = dday(project?.expected_issue_date)
  const imminent = isIssueImminent(dd)

  const handleDelete = async () => {
    if (!deleting) return
    try {
      await deleteMapping.mutateAsync(deleting.map_id)
      showToast('참여 고객사 매핑이 제거되었습니다.', 'success')
      setDeleting(null)
    } catch {
      showToast('제거에 실패했습니다. 정산 진행 건은 제거할 수 없습니다.', 'danger')
    }
  }

  // 대표자 = tb_project.client_id 일치 (SCR-06 §9-1 단일 소스 규칙)
  const isPrimary = (m: ProjectClientMap) =>
    project?.client_id != null && m.client_id === project.client_id

  const mappingColumns: Column<ProjectClientMap>[] = [
    {
      key: 'client',
      header: '고객사 (역할)',
      render: (m) => (
        <div className="flex items-center gap-1.5">
          <Link
            to={`/clients/${m.client_id}`}
            onClick={(e) => e.stopPropagation()}
            className="font-semibold text-bone hover:underline"
          >
            {m.client_name ?? '—'}
          </Link>
          <span
            className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold ${
              isPrimary(m)
                ? 'border-blue-400/25 bg-blue-500/15 text-blue-700 dark:text-blue-300'
                : 'border-hairline bg-elevate-strong text-ash'
            }`}
          >
            {isPrimary(m) ? '대표자' : '참여자'}
          </span>
        </div>
      ),
    },
    {
      key: 'asset',
      header: '연결 자산',
      render: (m) =>
        m.asset_id ? (
          <span className="text-xs text-ash">{m.asset_summary ?? m.asset_id}</span>
        ) : (
          <span className="text-xs text-smoke">—</span>
        ),
    },
    {
      key: 'ratio',
      header: '배분율',
      render: (m) => (
        <span className="text-sm font-semibold text-bone">
          {m.allocation_ratio != null ? `${Number(m.allocation_ratio)} %` : '—'}
        </span>
      ),
    },
    {
      key: 'fee',
      header: '보수율',
      render: (m) =>
        m.success_fee_rate != null ? (
          <SensitiveData type="rate" value={`${Number(m.success_fee_rate)} %`} />
        ) : (
          <span className="text-smoke">—</span>
        ),
    },
    {
      key: 'amount',
      header: '예상 정산액',
      render: (m) =>
        m.expected_amount != null ? (
          <SensitiveData type="money" value={fmtMoney(Number(m.expected_amount))} />
        ) : (
          /* 단가 미입력 → 서버 계산 불가 (§10.3) */
          <span className="text-xs font-medium text-amber-400">미정</span>
        ),
    },
    {
      key: 'settlement',
      header: '정산 상태',
      render: (m) => (
        /* 배지 클릭 → 정산 관리(SCR-07)로 직행 — 막다른 상태값 방지 */
        <Link
          to="/settlements"
          title="정산 관리에서 이 사업의 정산 현황 보기"
          className="inline-flex items-center gap-1 text-ash underline-offset-2 hover:underline"
        >
          <StatusBadge domain="settlement" value={m.settlement_status ?? 'STANDBY'} />
          <span className="text-xs font-medium">→</span>
        </Link>
      ),
    },
    {
      key: 'actions',
      header: '관리',
      className: 'text-right',
      render: (m) => (
        <div className="flex items-center justify-end gap-1">
          <button
            type="button"
            onClick={() => {
              setEditingMapping(m)
              setMappingOpen(true)
            }}
            className="rounded-md p-1.5 text-smoke hover:bg-elevate hover:text-bone"
            title="매핑 수정"
            aria-label={`${m.client_name ?? ''} 매핑 수정`}
          >
            <PencilSimple size={15} />
          </button>
          <button
            type="button"
            onClick={() => setDeleting(m)}
            disabled={(m.settlement_status ?? 'STANDBY') !== 'STANDBY'}
            className="rounded-md p-1.5 text-smoke hover:bg-rose-500/15 hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-30"
            title={m.settlement_status !== 'STANDBY' ? '정산 진행 건은 제거 불가' : '매핑 제거'}
            aria-label={`${m.client_name ?? ''} 매핑 제거`}
          >
            <Trash size={15} />
          </button>
        </div>
      ),
    },
  ]

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
          /* 수정 — 모바일 숨김 (§7.1) */
          <button
            type="button"
            onClick={() => setEditOpen(true)}
            className="hidden items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate sm:flex"
          >
            <PencilSimple size={15} />
            사업 수정
          </button>
        }
      />

      {/* 개요 카드 */}
      <section className="rounded-3xl border border-hairline bg-graphite p-5">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <StatusBadge domain="project" value={project.project_status} />
          {project.reg_code && (
            <span className="inline-flex items-center rounded border border-hairline bg-elevate px-1.5 py-0.5 font-mono text-[10px] text-ash">
              {project.reg_code}
            </span>
          )}
          <span className="text-xs text-slatey">참여 {mappings.length}개사</span>
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
          <OverviewItem label="예상 발행량">
            {project.expected_credits != null ? (
              <SensitiveData
                type="text"
                value={`${Number(project.expected_credits).toLocaleString('ko-KR')} tCO₂`}
              />
            ) : (
              '—'
            )}
          </OverviewItem>
          {project.issued_credits != null && (
            <OverviewItem label="확정 발급량">
              <SensitiveData
                type="text"
                value={`${Number(project.issued_credits).toLocaleString('ko-KR')} tCO₂`}
              />
              {project.issued_at && (
                <span className="ml-1.5 text-xs text-slatey">({fmtDate(project.issued_at)})</span>
              )}
            </OverviewItem>
          )}
          <OverviewItem label="배출권 단가 (수기 입력)">
            <UnitPriceEditor projectId={project.project_id} unitPrice={project.unit_price} />
          </OverviewItem>
        </div>
        {/* 공동 관리 가시화 — 등록/수정 일시 (작성자 조인은 백엔드 미제공) */}
        <p className="mt-4 border-t border-hairline pt-3 text-xs text-slatey">
          {project.created_at && `등록 ${fmtServerDateTime(project.created_at)}`}
          {project.updated_at && ` / 수정 ${fmtServerDateTime(project.updated_at)}`}
        </p>
      </section>

      {/* 참여 고객사 매핑 */}
      <section className="space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex items-baseline gap-3">
            <h2 className="text-base font-bold text-bone">참여 고객사 매핑</h2>
            {/* ClientDetailPage ProjectsTab 관용구 재사용 — 정산 관리(SCR-07) 직행 */}
            <Link
              to="/settlements"
              className="text-xs font-medium text-ash underline-offset-2 hover:underline"
            >
              정산 현황 전체 보기 →
            </Link>
          </div>
          {/* 매핑 편집 — 모바일 숨김 (§7.1) */}
          <button
            type="button"
            onClick={() => {
              setEditingMapping(null)
              setMappingOpen(true)
            }}
            className="hidden items-center gap-1.5 rounded-full bg-primary px-3.5 py-2 text-sm font-semibold text-on-primary hover:opacity-90 sm:flex"
          >
            <Plus size={15} weight="bold" />
            참여 고객사 추가
          </button>
        </div>

        {mappings.length > 0 && (
          <div className="rounded-3xl border border-hairline bg-graphite px-4 py-3">
            <AllocationGauge sum={allocationSum} />
          </div>
        )}

        <DataTable
          columns={mappingColumns}
          rows={mappings}
          rowKey={(m) => m.map_id}
          isLoading={isLoading}
          emptyTitle="참여 고객사가 없습니다"
          emptyDescription="[참여 고객사 추가]로 배분율·보수율을 매핑해 보세요."
          renderCard={(m) => (
            /* 모바일 카드 — 열람 전용 (§7) */
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <p className="font-semibold text-bone">{m.client_name ?? '—'}</p>
                  <span className="text-[10px] font-semibold text-slatey">
                    {isPrimary(m) ? '대표자' : '참여자'}
                  </span>
                </div>
                <StatusBadge domain="settlement" value={m.settlement_status ?? 'STANDBY'} />
              </div>
              <div className="flex items-center justify-between border-t border-hairline pt-2 text-sm">
                <span className="text-ash">
                  배분율{' '}
                  <b className="text-bone">
                    {m.allocation_ratio != null ? `${Number(m.allocation_ratio)} %` : '—'}
                  </b>
                </span>
                {m.expected_amount != null ? (
                  <SensitiveData type="money" value={fmtMoney(Number(m.expected_amount))} />
                ) : (
                  <span className="text-xs font-medium text-amber-400">미정</span>
                )}
              </div>
            </div>
          )}
        />
      </section>

      <ProjectFormModal open={editOpen} onClose={() => setEditOpen(false)} project={project} />
      {projectId && (
        <MappingFormModal
          open={mappingOpen}
          onClose={() => setMappingOpen(false)}
          projectId={projectId}
          mapping={editingMapping}
          mappings={mappings}
        />
      )}
      <ConfirmDialog
        open={!!deleting}
        title="참여 고객사 매핑 제거"
        message={
          <>
            <b>{deleting?.client_name ?? ''}</b>의 매핑을 제거합니다. 배분율 합계가 변경되며, 이
            작업은 되돌릴 수 없습니다.
          </>
        }
        confirmLabel="제거"
        danger
        loading={deleteMapping.isPending}
        onConfirm={handleDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  )
}
