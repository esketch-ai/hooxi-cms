// SCR-02 이슈 보드 — 팀 공용 칸반 (접수→처리중→보류→완료)
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarCheck, Buildings, Fire, Kanban, Plus, Spinner } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { KpiCard } from '../../components/KpiCard'
import { KanbanBoard, type KanbanColumn } from '../../components/KanbanBoard'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonKpi } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import { api } from '../../lib/api/client'
import { unwrapList, useClientOptions, useCodes, useUserOptions } from '../../lib/api/queries'
import { dotClassOf } from '../../lib/codePalette'
import { dday, elapsedServer, fmtDate, parseServerUtc } from '../../lib/format'
import type { ActivityHistory, IssueStatus, Paginated, Schedule } from '../../types'
import { ActivityForm } from '../histories/ActivityForm'
import { useChangeIssueStatus, useIssues } from './api'
import { IssueDrawer } from './IssueDrawer'

// 코드 미로딩 시 폴백 컬럼 (기존 고정값)
const FALLBACK_COLUMNS: KanbanColumn[] = [
  { key: 'OPEN', title: '접수', dotClass: 'bg-rose-500' },
  { key: 'IN_PROGRESS', title: '처리중', dotClass: 'bg-amber-400' },
  { key: 'HOLD', title: '보류/지연', dotClass: 'bg-slate-400' },
  { key: 'CLOSED', title: '완료 (최근 7일)', dotClass: 'bg-emerald-500', collapsible: true },
]

type PillFilter = 'ALL' | 'MINE' | 'URGENT'

export function IssuesPage() {
  const { user } = useAuth()
  const { showToast } = useToast()
  const { data: issues = [], isLoading, isError, refetch } = useIssues()
  const { data: clients = [] } = useClientOptions()
  const { data: users = [] } = useUserOptions()
  const { codes: issueStatusCodes } = useCodes('ISSUE_STATUS')
  const changeStatus = useChangeIssueStatus()

  // 이슈 상태 코드(활성)에서 칸반 컬럼 생성 — 색상·순서·표시명이 마스터 반영.
  // CLOSED는 접힘 + '(최근 7일)' 표기 유지. 미로딩 시 폴백.
  const columns = useMemo<KanbanColumn[]>(() => {
    const active = issueStatusCodes.filter((c) => c.active === 'Y')
    if (active.length === 0) return FALLBACK_COLUMNS
    return active.map((c) => ({
      key: c.code,
      title: c.code === 'CLOSED' ? `${c.label} (최근 7일)` : c.label,
      dotClass: dotClassOf(c.color),
      collapsible: c.code === 'CLOSED',
    }))
  }, [issueStatusCodes])

  const [scope, setScope] = useState<'team' | 'mine'>('team') // 요약 카드 토글
  const [pill, setPill] = useState<PillFilter>('ALL')
  const [managerFilter, setManagerFilter] = useState('') // 담당자별
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)

  // 오늘의 일정 (금일 예정 카드)
  const todayStr = fmtDate(new Date())
  const { data: todaySchedules = [] } = useQuery({
    queryKey: ['schedules', 'today'],
    queryFn: async () => {
      const { data } = await api.get<Schedule[] | Paginated<Schedule>>('/schedules', {
        params: { date_from: todayStr, date_to: todayStr },
      })
      return unwrapList(data).items
    },
    retry: false,
  })

  // 요약 카드 (팀 전체 ↔ 내 것)
  const summary = useMemo(() => {
    const inScope = <T extends { manager_id?: string | null }>(rows: T[]) =>
      scope === 'mine' ? rows.filter((r) => r.manager_id === user?.user_id) : rows
    const scopedIssues = inScope(issues)
    const open = scopedIssues.filter((i) => i.issue_status !== 'CLOSED')
    const urgentToday = open.filter((i) => {
      if (i.priority === 'URGENT') return true
      const d = dday(i.due_date)
      return !!d && (d.overdue || d.label === 'D-DAY')
    })
    return {
      clients: inScope(clients).length,
      urgentToday: urgentToday.length,
      inProgress: scopedIssues.filter((i) => i.issue_status === 'IN_PROGRESS').length,
      todayPlanned: inScope(todaySchedules).filter((s) => s.status === 'PLANNED').length,
    }
  }, [issues, clients, todaySchedules, scope, user?.user_id])

  // 칸반 필터: 완료 컬럼은 최근 7일만
  const visibleIssues = useMemo(() => {
    const weekAgo = Date.now() - 7 * 86_400_000
    return issues.filter((i) => {
      if (pill === 'MINE' && i.manager_id !== user?.user_id) return false
      if (pill === 'URGENT' && i.priority !== 'URGENT') return false
      if (managerFilter && i.manager_id !== managerFilter) return false
      if (i.issue_status === 'CLOSED') {
        const t = parseServerUtc(i.updated_at ?? i.created_at ?? '').getTime()
        return !Number.isNaN(t) && t >= weekAgo
      }
      return true
    })
  }, [issues, pill, managerFilter, user?.user_id])

  const selected = issues.find((i) => i.history_id === selectedId) ?? null

  const handleMove = async (id: string, toColumn: string) => {
    const issue = issues.find((i) => i.history_id === id)
    if (!issue || issue.issue_status === toColumn) return
    try {
      await changeStatus.mutateAsync({ historyId: id, issueStatus: toColumn as IssueStatus })
      showToast('이슈 상태가 변경되었습니다.', 'success')
    } catch {
      showToast('상태 변경에 실패했습니다.', 'danger')
    }
  }

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="이슈 보드"
        subtitle="팀 공용 칸반 — 부서원 전원이 함께 처리"
        actions={
          <button
            type="button"
            onClick={() => setFormOpen(true)}
            className="hidden items-center gap-1.5 rounded-full bg-primary px-3.5 py-2 text-sm font-medium text-on-primary hover:opacity-90 sm:flex"
          >
            <Plus size={16} weight="bold" />
            이슈 등록
          </button>
        }
      />

      {/* 요약 4카드 + 팀/내것 토글 */}
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-slatey">
          {scope === 'team' ? '팀 전체 현황' : '내 담당 현황'}
        </p>
        <div className="flex rounded-lg border border-hairline bg-graphite p-0.5">
          {(['team', 'mine'] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setScope(s)}
              className={`rounded-md px-3 py-1 text-xs font-medium ${
                scope === s ? 'bg-primary text-on-primary' : 'text-ash hover:text-bone'
              }`}
            >
              {s === 'team' ? '팀 전체' : '내 것'}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <SkeletonKpi count={4} />
      ) : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiCard title="관리 고객사" value={summary.clients} icon={<Buildings size={18} />} />
          <KpiCard
            title="오늘 마감 · 긴급"
            value={summary.urgentToday}
            variant="danger"
            icon={<Fire size={18} />}
          />
          <KpiCard title="처리 중" value={summary.inProgress} icon={<Spinner size={18} />} />
          <KpiCard
            title="금일 예정"
            value={summary.todayPlanned}
            icon={<CalendarCheck size={18} />}
            sub="오늘의 일정 기준"
          />
        </div>
      )}

      {/* 필터 pill */}
      <div className="flex flex-wrap items-center gap-1.5">
        {(
          [
            { key: 'ALL', label: '전체' },
            { key: 'MINE', label: '내 담당' },
            { key: 'URGENT', label: '긴급만' },
          ] as { key: PillFilter; label: string }[]
        ).map((p) => (
          <button
            key={p.key}
            type="button"
            onClick={() => {
              setPill(p.key)
              if (p.key !== 'ALL') setManagerFilter('')
            }}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
              pill === p.key && !managerFilter
                ? 'border-snow bg-primary text-on-primary'
                : 'border-hairline text-bone hover:bg-elevate'
            }`}
          >
            {p.label}
          </button>
        ))}
        <select
          value={managerFilter}
          onChange={(e) => {
            setManagerFilter(e.target.value)
            if (e.target.value) setPill('ALL')
          }}
          className={`h-8 rounded-full border px-2.5 text-xs font-medium focus:outline-none ${
            managerFilter
              ? 'border-snow bg-primary text-on-primary'
              : 'border-hairline bg-graphite text-bone'
          }`}
          aria-label="담당자별 필터"
        >
          <option value="">담당자별</option>
          {users.map((u) => (
            <option key={u.user_id} value={u.user_id}>
              {u.name}
            </option>
          ))}
        </select>
      </div>

      {/* 칸반 */}
      {isError ? (
        <EmptyState
          icon={<Kanban size={36} />}
          title="이슈를 불러오지 못했습니다"
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
        <KanbanBoard
          columns={columns}
          items={visibleIssues}
          itemKey={(i) => i.history_id}
          columnOf={(i) => i.issue_status ?? 'OPEN'}
          onMove={handleMove}
          onCardClick={(i) => setSelectedId(i.history_id)}
          renderCard={(i) => <IssueCard issue={i} />}
        />
      )}

      <IssueDrawer issue={selected} onClose={() => setSelectedId(null)} />
      <ActivityForm open={formOpen} onClose={() => setFormOpen(false)} defaultType="ISSUE" />
    </div>
  )
}

/** 칸반 카드 — 고객사·요약·긴급도·담당자 아바타·경과 시간 */
function IssueCard({ issue }: { issue: ActivityHistory }) {
  const due = dday(issue.due_date)
  const urgent = issue.priority === 'URGENT'
  const actionable = urgent || (due && (due.overdue || due.imminent))
  return (
    <div
      className={`rounded-2xl border bg-graphite p-3 transition-colors hover:bg-elevate ${
        actionable && issue.issue_status !== 'CLOSED'
          ? 'border-rose-400/40 ring-1 ring-rose-500/20'
          : 'border-hairline'
      }`}
    >
      <div className="flex items-center gap-1.5">
        <p className="min-w-0 flex-1 truncate text-xs font-semibold text-ash">
          {issue.client_name ?? (issue.client_id ? '고객사' : '미지정 고객')}
        </p>
        {urgent && (
          <span className="shrink-0 rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] font-bold text-rose-700 dark:text-rose-300">
            긴급
          </span>
        )}
      </div>
      <p className="mt-1 line-clamp-2 text-sm font-medium text-bone">{issue.title}</p>
      <div className="mt-2.5 flex items-center gap-2">
        <span
          className="flex h-6 w-6 items-center justify-center rounded-full bg-elevate-strong text-[10px] font-bold text-bone"
          title={issue.manager_name ?? '담당자'}
        >
          {(issue.manager_name ?? '?').charAt(0)}
        </span>
        <span className="text-[11px] text-slatey">{elapsedServer(issue.created_at)}</span>
        {due && issue.issue_status !== 'CLOSED' && (
          <span
            className={`ml-auto text-[11px] font-semibold ${
              due.overdue || due.imminent ? 'text-rose-700 dark:text-rose-300' : 'text-slatey'
            }`}
          >
            {due.label}
          </span>
        )}
      </div>
    </div>
  )
}
