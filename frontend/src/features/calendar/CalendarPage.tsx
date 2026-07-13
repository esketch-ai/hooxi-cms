// SCR-11 일정 캘린더 — 월간/주간 뷰 + 담당자 색상 도트 + 오늘의 일정 체크리스트
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CalendarDots,
  CaretLeft,
  CaretRight,
  CheckCircle,
  CircleNotch,
  MapPin,
  Phone,
  Plus,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { CalendarView, type CalendarEventItem } from '../../components/CalendarView'
import { EmptyState } from '../../components/EmptyState'
import { Modal } from '../../components/Modal'
import { Skeleton } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import { api } from '../../lib/api/client'
import { unwrapList, useUserOptions } from '../../lib/api/queries'
import { fmtDate, fmtDateTime, fmtTime, telHref } from '../../lib/format'
import type { Paginated, Schedule } from '../../types'
import { ScheduleFormModal } from './ScheduleFormModal'

// 담당자 색상 도트 팔레트 — manager_id 해시로 안정 배정
const MANAGER_COLORS = [
  'bg-blue-500',
  'bg-emerald-500',
  'bg-amber-500',
  'bg-purple-500',
  'bg-rose-500',
  'bg-cyan-500',
  'bg-indigo-500',
  'bg-lime-600',
]

function managerColor(managerId?: string | null): string {
  if (!managerId) return 'bg-slate-400'
  let hash = 0
  for (let i = 0; i < managerId.length; i++) {
    hash = (hash * 31 + managerId.charCodeAt(i)) >>> 0
  }
  return MANAGER_COLORS[hash % MANAGER_COLORS.length]
}

const TYPE_LABELS: Record<string, string> = {
  MEETING: '미팅',
  CALL: '전화',
  SITE_VISIT: '현장방문',
  REPORT_DUE: '보고서 마감',
  INTERNAL: '내부 일정',
}

export function CalendarPage() {
  const { user } = useAuth()
  const { showToast } = useToast()
  const { data: users = [] } = useUserOptions()
  const queryClient = useQueryClient()

  const [mode, setMode] = useState<'month' | 'week'>('month')
  const [cursor, setCursor] = useState(() => new Date())
  const [typeFilter, setTypeFilter] = useState('')
  const [scopeFilter, setScopeFilter] = useState('') // '' 전체 / 'mine' / user_id
  const [formOpen, setFormOpen] = useState(false)
  const [formDate, setFormDate] = useState<Date | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // 조회 범위: 표시 월(±1주) 또는 주
  const range = useMemo(() => {
    if (mode === 'month') {
      const from = new Date(cursor.getFullYear(), cursor.getMonth(), 1)
      from.setDate(from.getDate() - 7)
      const to = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0)
      to.setDate(to.getDate() + 7)
      return { from: fmtDate(from), to: fmtDate(to) }
    }
    const start = new Date(cursor)
    start.setDate(start.getDate() - start.getDay())
    const end = new Date(start)
    end.setDate(start.getDate() + 6)
    return { from: fmtDate(start), to: fmtDate(end) }
  }, [mode, cursor])

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['schedules', range],
    queryFn: async () => {
      const { data } = await api.get<Schedule[] | Paginated<Schedule>>('/schedules', {
        params: { date_from: range.from, date_to: range.to },
      })
      return unwrapList(data).items
    },
  })
  const schedules = data ?? []

  const filtered = useMemo(
    () =>
      schedules.filter((s) => {
        if (typeFilter && s.schedule_type !== typeFilter) return false
        if (scopeFilter === 'mine') return s.manager_id === user?.user_id
        if (scopeFilter) return s.manager_id === scopeFilter
        return true
      }),
    [schedules, typeFilter, scopeFilter, user?.user_id],
  )

  const events: CalendarEventItem<Schedule>[] = filtered.map((s) => ({
    id: s.schedule_id,
    start: new Date(s.start_at),
    title: s.title,
    dotClass: managerColor(s.manager_id),
    muted: s.status !== 'PLANNED',
    data: s,
  }))

  // 오늘의 일정 (시간순)
  const today = new Date()
  const todayList = useMemo(
    () =>
      schedules
        .filter((s) => {
          const d = new Date(s.start_at)
          return (
            d.getFullYear() === today.getFullYear() &&
            d.getMonth() === today.getMonth() &&
            d.getDate() === today.getDate()
          )
        })
        .sort((a, b) => a.start_at.localeCompare(b.start_at)),
    [schedules], // eslint-disable-line react-hooks/exhaustive-deps
  )

  const move = (delta: number) => {
    const next = new Date(cursor)
    if (mode === 'month') next.setMonth(next.getMonth() + delta)
    else next.setDate(next.getDate() + delta * 7)
    setCursor(next)
  }

  const selected = schedules.find((s) => s.schedule_id === selectedId) ?? null

  const headerLabel =
    mode === 'month'
      ? `${cursor.getFullYear()}년 ${cursor.getMonth() + 1}월`
      : `${range.from} ~ ${range.to}`

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="일정 캘린더"
        subtitle="부서 전체 일정 — 담당자별 색상 도트"
        actions={
          <button
            type="button"
            onClick={() => {
              setFormDate(null)
              setFormOpen(true)
            }}
            className="hidden items-center gap-1.5 rounded-full bg-primary px-3.5 py-2 text-sm font-medium text-on-primary hover:opacity-90 sm:flex"
          >
            <Plus size={16} weight="bold" />
            일정 등록
          </button>
        }
      />

      {/* 툴바 */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => move(-1)}
            className="flex h-8 w-8 items-center justify-center rounded-md border border-hairline text-ash hover:bg-elevate"
            aria-label="이전"
          >
            <CaretLeft size={14} />
          </button>
          <button
            type="button"
            onClick={() => setCursor(new Date())}
            className="h-8 rounded-md border border-hairline px-3 text-xs font-medium text-bone hover:bg-elevate"
          >
            오늘
          </button>
          <button
            type="button"
            onClick={() => move(1)}
            className="flex h-8 w-8 items-center justify-center rounded-md border border-hairline text-ash hover:bg-elevate"
            aria-label="다음"
          >
            <CaretRight size={14} />
          </button>
        </div>
        <h2 className="text-base font-bold text-bone">{headerLabel}</h2>
        <div className="ml-auto flex items-center gap-2">
          <select
            value={scopeFilter}
            onChange={(e) => setScopeFilter(e.target.value)}
            className="h-8 rounded-lg border border-hairline bg-graphite px-2 text-xs text-bone focus:outline-none"
            aria-label="담당자 필터"
          >
            <option value="">전체 일정</option>
            <option value="mine">내 일정</option>
            {users
              .filter((u) => u.user_id !== user?.user_id)
              .map((u) => (
                <option key={u.user_id} value={u.user_id}>
                  {u.name}
                </option>
              ))}
          </select>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="h-8 rounded-lg border border-hairline bg-graphite px-2 text-xs text-bone focus:outline-none"
            aria-label="유형 필터"
          >
            <option value="">전체 유형</option>
            {Object.entries(TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <div className="flex rounded-lg border border-hairline bg-graphite p-0.5">
            {(['month', 'week'] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`rounded-md px-3 py-1 text-xs font-medium ${
                  mode === m ? 'bg-primary text-on-primary' : 'text-ash hover:text-bone'
                }`}
              >
                {m === 'month' ? '월간' : '주간'}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
        {/* 캘린더 본체 */}
        <div>
          {isLoading ? (
            <div className="rounded-3xl border border-hairline bg-graphite p-5">
              <Skeleton className="h-96 w-full" />
            </div>
          ) : isError ? (
            <EmptyState
              icon={<CalendarDots size={36} />}
              title="일정을 불러오지 못했습니다"
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
            <CalendarView
              mode={mode}
              cursor={cursor}
              events={events}
              onEventClick={(s) => setSelectedId(s.schedule_id)}
              onDayClick={(d) => {
                setFormDate(d)
                setFormOpen(true)
              }}
            />
          )}
        </div>

        {/* 오늘의 일정 체크리스트 */}
        <TodayChecklist
          items={todayList}
          onSelect={(s) => setSelectedId(s.schedule_id)}
          onDone={() =>
            queryClient.invalidateQueries({ queryKey: ['schedules'] })
          }
        />
      </div>

      <ScheduleFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        defaultDate={formDate}
      />
      <ScheduleDetailModal schedule={selected} onClose={() => setSelectedId(null)} />
    </div>
  )
}

// ── 일정 클릭 상세 ──────────────────────────────────────────────────
function ScheduleDetailModal({
  schedule,
  onClose,
}: {
  schedule: Schedule | null
  onClose: () => void
}) {
  if (!schedule) return null
  return (
    <Modal open onClose={onClose} title={schedule.title} size="md">
        <dl className="space-y-2.5 text-sm">
          <div className="flex gap-2">
            <dt className="w-20 shrink-0 text-xs font-medium text-slatey">유형</dt>
            <dd className="flex items-center gap-2 text-bone">
              <span
                className={`h-2 w-2 rounded-full ${managerColor(schedule.manager_id)}`}
                aria-hidden="true"
              />
              {TYPE_LABELS[schedule.schedule_type] ?? schedule.schedule_type}
              {schedule.status !== 'PLANNED' && (
                <span className="text-xs text-slatey">
                  ({schedule.status === 'DONE' ? '완료' : '취소'})
                </span>
              )}
            </dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-20 shrink-0 text-xs font-medium text-slatey">일시</dt>
            <dd className="text-bone">
              {fmtDateTime(schedule.start_at)}
              {schedule.end_at ? ` ~ ${fmtTime(schedule.end_at)}` : ''}
            </dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-20 shrink-0 text-xs font-medium text-slatey">담당자</dt>
            <dd className="text-bone">{schedule.manager_name ?? '—'}</dd>
          </div>
          {schedule.client_id && (
            <div className="flex gap-2">
              <dt className="w-20 shrink-0 text-xs font-medium text-slatey">고객사</dt>
              <dd>
                <Link
                  to={`/clients/${schedule.client_id}`}
                  className="font-semibold text-bone hover:underline"
                  onClick={onClose}
                >
                  {schedule.client_name ?? '고객사 상세 →'}
                </Link>
              </dd>
            </div>
          )}
          {schedule.location && (
            <div className="flex gap-2">
              <dt className="w-20 shrink-0 text-xs font-medium text-slatey">장소</dt>
              <dd className="flex items-center gap-1 text-bone">
                <MapPin size={14} className="text-slatey" />
                {schedule.location}
              </dd>
            </div>
          )}
          {schedule.memo && (
            <div className="flex gap-2">
              <dt className="w-20 shrink-0 text-xs font-medium text-slatey">메모</dt>
              <dd className="whitespace-pre-wrap text-bone">{schedule.memo}</dd>
            </div>
          )}
          {schedule.schedule_type === 'REPORT_DUE' && (
            <p className="rounded-lg bg-elevate px-3 py-2 text-xs text-ash">
              보고서 마감 일정은 월간 보고서 발송 관리(SCR-12)에서 자동 생성됩니다.
            </p>
          )}
        </dl>
    </Modal>
  )
}

// ── 오늘의 일정 체크리스트 (완료 시 조치 결과 인라인 입력) ─────────────
function TodayChecklist({
  items,
  onSelect,
  onDone,
}: {
  items: Schedule[]
  onSelect: (s: Schedule) => void
  onDone: () => void
}) {
  const { showToast } = useToast()
  const [completingId, setCompletingId] = useState<string | null>(null)
  const [resultNote, setResultNote] = useState('')

  const complete = useMutation({
    mutationFn: async ({ scheduleId, note }: { scheduleId: string; note: string }) => {
      // 완료 처리 → 백엔드가 활동 이력 "[자동]" 적재 (result_note = 조치 결과)
      const { data } = await api.put(`/schedules/${scheduleId}`, {
        status: 'DONE',
        result_note: note || undefined,
      })
      return data
    },
  })

  const handleComplete = async (scheduleId: string) => {
    try {
      await complete.mutateAsync({ scheduleId, note: resultNote.trim() })
      showToast('일정이 완료 처리되었습니다. 활동 이력에 자동 기록됩니다.', 'success')
      setCompletingId(null)
      setResultNote('')
      onDone()
    } catch {
      showToast('완료 처리에 실패했습니다.', 'danger')
    }
  }

  return (
    <aside className="h-fit rounded-3xl border border-hairline bg-graphite p-4">
      <h2 className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-bone">
        <CheckCircle size={16} className="text-emerald-400" />
        오늘의 일정
        <span className="ml-auto text-xs font-normal text-slatey">
          {items.filter((s) => s.status === 'DONE').length}/{items.length} 완료
        </span>
      </h2>
      {items.length === 0 ? (
        <p className="rounded-lg border border-dashed border-hairline py-6 text-center text-xs text-slatey">
          오늘 일정이 없습니다
        </p>
      ) : (
        <ul className="space-y-1">
          {items.map((s) => {
            const done = s.status === 'DONE'
            const canceled = s.status === 'CANCELED'
            const isCompleting = completingId === s.schedule_id
            return (
              <li key={s.schedule_id} className="rounded-lg px-1 py-1.5 hover:bg-elevate">
                <div className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={done}
                    disabled={done || canceled}
                    onChange={() => {
                      setCompletingId(s.schedule_id)
                      setResultNote('')
                    }}
                    className="mt-0.5 h-4 w-4 shrink-0 rounded border-hairline-strong"
                    aria-label={`${s.title} 완료`}
                  />
                  <button
                    type="button"
                    onClick={() => onSelect(s)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <p
                      className={`truncate text-sm ${
                        done || canceled
                          ? 'text-slatey line-through'
                          : 'font-medium text-bone'
                      }`}
                    >
                      <span className="mr-1.5 font-mono text-xs text-slatey">
                        {fmtTime(s.start_at)}
                      </span>
                      {s.title}
                    </p>
                    <p className="text-[11px] text-slatey">
                      {s.client_name ?? '내부'} · {s.manager_name ?? ''}
                    </p>
                  </button>
                  {/* 모바일 Click-to-Call */}
                  {s.client_phone && !done && (
                    <a
                      href={telHref(s.client_phone)}
                      className="rounded-md p-1.5 text-emerald-400 hover:bg-emerald-500/10 sm:hidden"
                      aria-label="전화 걸기"
                    >
                      <Phone size={16} weight="fill" />
                    </a>
                  )}
                </div>
                {/* 완료 시 조치 결과 인라인 입력 → 활동 이력 자동 기록 */}
                {isCompleting && (
                  <div className="animate-fade-in mt-2 ml-6 space-y-1.5">
                    <input
                      value={resultNote}
                      onChange={(e) => setResultNote(e.target.value)}
                      placeholder="조치 결과 입력 (활동 이력에 기록)"
                      className="h-9 w-full rounded-lg border border-hairline bg-graphite px-2.5 text-xs text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
                      autoFocus
                    />
                    <div className="flex justify-end gap-1.5">
                      <button
                        type="button"
                        onClick={() => setCompletingId(null)}
                        className="rounded-full border border-hairline px-2.5 py-1 text-xs text-bone hover:bg-elevate"
                      >
                        취소
                      </button>
                      <button
                        type="button"
                        onClick={() => handleComplete(s.schedule_id)}
                        disabled={complete.isPending}
                        className="flex items-center gap-1 rounded-full bg-primary px-2.5 py-1 text-xs font-medium text-on-primary hover:opacity-90 disabled:opacity-60"
                      >
                        {complete.isPending && (
                          <CircleNotch size={11} className="animate-spin" />
                        )}
                        완료 처리
                      </button>
                    </div>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {/* 담당자 색상 범례는 일정 도트와 동일 규칙 */}
      <p className="mt-3 border-t border-hairline pt-2 text-[11px] text-slatey">
        캘린더 도트 색상은 담당자별 자동 배정 · 완료 일정은 취소선 표시
      </p>
    </aside>
  )
}
