// SCR-06 감축 사업 관리 목록 — "돈이 언제 들어오는가" 즉답 화면
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { CaretRight, Plus, Receipt, TreeEvergreen } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { FilterBar, FilterSearch, FilterSelect } from '../../components/FilterBar'
import { DataTable, type Column } from '../../components/DataTable'
import { Pagination } from '../../components/Pagination'
import { StatusBadge } from '../../components/StatusBadge'
import { SensitiveData } from '../../components/SensitiveData'
import { EmptyState } from '../../components/EmptyState'
import { useUserOptions } from '../../lib/api/queries'
import { dday, fmtDate } from '../../lib/format'
import type { Project } from '../../types'
import { isIssueImminent, MON_CYCLE_OPTIONS, PROJECT_STATUS_OPTIONS, useProjects } from './api'
import { ProjectFormModal } from './ProjectFormModal'

const PAGE_SIZE = 20

/** 사업명 + 고유번호 mono pill + 참여 N개사 */
export function ProjectNameCell({ project, link = true }: { project: Project; link?: boolean }) {
  const name = link ? (
    <Link
      to={`/projects/${project.project_id}`}
      onClick={(e) => e.stopPropagation()}
      className="block truncate font-semibold text-bone hover:underline"
    >
      {project.project_name}
    </Link>
  ) : (
    <p className="truncate font-semibold text-bone">{project.project_name}</p>
  )
  return (
    <div className="min-w-0">
      {name}
      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        {project.reg_code && (
          <span className="inline-flex items-center rounded border border-hairline bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-ash">
            {project.reg_code}
          </span>
        )}
        {project.client_count != null && (
          <span className="text-xs text-slatey">참여 {project.client_count}개사</span>
        )}
      </div>
    </div>
  )
}

/** 예상 발급일 + D-day — 7일 이내·경과 시 빨강 (SCR-06 §4.1) */
export function IssueDateCell({ date, className = '' }: { date?: string | null; className?: string }) {
  if (!date) return <span className="text-xs text-slatey">미정</span>
  const dd = dday(date)
  const imminent = isIssueImminent(dd)
  return (
    <div className={className}>
      <p className="text-sm text-bone">{fmtDate(date)}</p>
      {dd && (
        <span
          className={`text-xs font-bold ${imminent ? 'text-rose-400' : 'text-slatey'}`}
        >
          {dd.label}
        </span>
      )}
    </div>
  )
}

/** 기간 표시 'YYYY-MM-DD ~ YYYY-MM-DD' */
function periodLabel(start?: string | null, end?: string | null): string {
  if (!start && !end) return '기간 미정'
  return `${start ? fmtDate(start) : '—'} ~ ${end ? fmtDate(end) : '—'}`
}

export function ProjectsPage() {
  const navigate = useNavigate()
  const { data: users = [] } = useUserOptions()

  const [projectStatus, setProjectStatus] = useState('')
  const [managerId, setManagerId] = useState('')
  const [monCycle, setMonCycle] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [formOpen, setFormOpen] = useState(false)

  const filters = useMemo(
    () => ({
      project_status: projectStatus,
      manager_id: managerId,
      mon_cycle: monCycle,
      search,
      page,
      page_size: PAGE_SIZE,
    }),
    [projectStatus, managerId, monCycle, search, page],
  )

  const { data, isLoading, isError, refetch } = useProjects(filters)
  const rows = data?.items ?? []
  const total = data?.total ?? 0

  const columns: Column<Project>[] = [
    {
      key: 'name',
      header: '사업명 / 고유번호',
      className: 'min-w-[220px]',
      render: (p) => <ProjectNameCell project={p} />,
    },
    {
      key: 'status',
      header: '진행 상태',
      render: (p) => <StatusBadge domain="project" value={p.project_status} />,
    },
    {
      key: 'period',
      header: '유효 / 모니터링 기간',
      render: (p) => (
        <div className="text-xs text-ash">
          <p>유효 {periodLabel(p.credit_start_date, p.credit_end_date)}</p>
          <p className="mt-0.5">
            모니터링 {periodLabel(p.mon_start_date, p.mon_end_date)}
            {p.mon_cycle ? ` (${p.mon_cycle})` : ''}
          </p>
        </div>
      ),
    },
    {
      key: 'credits',
      header: '예상 발행량',
      render: (p) =>
        p.expected_credits != null ? (
          <SensitiveData
            type="text"
            value={`${Number(p.expected_credits).toLocaleString('ko-KR')} tCO₂`}
          />
        ) : (
          <span className="text-smoke">—</span>
        ),
    },
    {
      key: 'issueDate',
      header: '예상 발급일',
      render: (p) => <IssueDateCell date={p.expected_issue_date} />,
    },
    {
      key: 'actions',
      header: '관리',
      className: 'text-right',
      render: (p) => {
        const planning = p.project_status === '기획'
        return (
          <div className="flex items-center justify-end gap-1">
            <Link
              to={`/projects/${p.project_id}`}
              onClick={(e) => e.stopPropagation()}
              className="rounded-md p-1.5 text-smoke hover:bg-white/5 hover:text-bone"
              title="상세"
              aria-label={`${p.project_name} 상세`}
            >
              <CaretRight size={16} />
            </Link>
            {planning ? (
              /* 기획 단계는 정산 매핑 비활성 (SCR-06 §6) */
              <span
                className="cursor-not-allowed rounded-md p-1.5 text-slatey"
                title="등록 완료 후 매핑 가능"
                aria-disabled="true"
              >
                <Receipt size={16} />
              </span>
            ) : (
              <Link
                to={`/settlements?project_id=${p.project_id}`}
                onClick={(e) => e.stopPropagation()}
                className="rounded-md p-1.5 text-smoke hover:bg-white/5 hover:text-bone"
                title="정산 매핑"
                aria-label={`${p.project_name} 정산 매핑`}
              >
                <Receipt size={16} />
              </Link>
            )}
          </div>
        )
      },
    },
  ]

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="감축 사업 관리"
        subtitle="사업별 진행 상태·배출권 예상 발급일 추적"
        actions={
          /* 신규 등록 — 모바일 숨김 (§7.1) */
          <button
            type="button"
            onClick={() => setFormOpen(true)}
            className="hidden items-center gap-1.5 rounded-full bg-snow px-3.5 py-2 text-sm font-semibold text-graphite hover:bg-white/90 sm:flex"
          >
            <Plus size={16} weight="bold" />
            신규 사업 등록
          </button>
        }
      />

      <FilterBar>
        <FilterSelect
          label="진행 상태"
          value={projectStatus}
          onChange={(v) => {
            setProjectStatus(v)
            setPage(1)
          }}
          options={PROJECT_STATUS_OPTIONS}
        />
        <FilterSelect
          label="담당 PM"
          value={managerId}
          onChange={(v) => {
            setManagerId(v)
            setPage(1)
          }}
          options={users.map((u) => ({ value: u.user_id, label: u.name }))}
        />
        <FilterSelect
          label="모니터링 주기"
          value={monCycle}
          onChange={(v) => {
            setMonCycle(v)
            setPage(1)
          }}
          options={MON_CYCLE_OPTIONS}
        />
        <FilterSearch
          value={search}
          onChange={(v) => {
            setSearch(v)
            setPage(1)
          }}
          placeholder="사업명·고유번호 검색"
          className="min-w-[200px] flex-1"
        />
      </FilterBar>

      {isError ? (
        <EmptyState
          icon={<TreeEvergreen size={36} />}
          title="목록을 불러오지 못했습니다"
          description="네트워크 상태를 확인한 뒤 다시 시도해 주세요."
          action={
            <button
              type="button"
              onClick={() => refetch()}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-white/5"
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
            rowKey={(p) => p.project_id}
            isLoading={isLoading}
            onRowClick={(p) => navigate(`/projects/${p.project_id}`)}
            emptyTitle="등록된 사업이 없습니다"
            emptyDescription="우측 상단 [신규 사업 등록]으로 첫 감축 사업을 등록해 보세요."
            renderCard={(p) => (
              /* 모바일 카드 — 사업명·상태·발급일 D-day 크게 (SCR-06 §8) */
              <Link to={`/projects/${p.project_id}`} className="block space-y-2.5">
                <div className="flex items-start justify-between gap-2">
                  <ProjectNameCell project={p} link={false} />
                  <StatusBadge domain="project" value={p.project_status} />
                </div>
                <div className="flex items-end justify-between border-t border-hairline pt-2">
                  <div>
                    <p className="text-[10px] font-medium tracking-wider text-slatey uppercase">
                      예상 발급일
                    </p>
                    <IssueDateCell date={p.expected_issue_date} className="mt-0.5" />
                  </div>
                  <span className="text-xs text-slatey">
                    {p.mon_cycle ? `모니터링 ${p.mon_cycle}` : ''}
                  </span>
                </div>
              </Link>
            )}
          />
          {total > 0 && (
            <Pagination total={total} page={page} pageSize={PAGE_SIZE} onChange={setPage} />
          )}
        </>
      )}

      <ProjectFormModal open={formOpen} onClose={() => setFormOpen(false)} />
    </div>
  )
}
