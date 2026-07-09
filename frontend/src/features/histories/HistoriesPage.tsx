// SCR-05 영업 활동 이력 — 아코디언 테이블 + 공용 ActivityForm
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CaretDown, ClockCounterClockwise, Plus } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { FilterBar, FilterSearch, FilterSelect } from '../../components/FilterBar'
import { Pagination } from '../../components/Pagination'
import { StatusBadge } from '../../components/StatusBadge'
import { AuditLine } from '../../components/AuditLine'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonTableRows } from '../../components/Skeleton'
import { api } from '../../lib/api/client'
import { unwrapList, useUserOptions } from '../../lib/api/queries'
import { fmtDateTime } from '../../lib/format'
import type { ActivityHistory, Paginated } from '../../types'
import { ActivityForm } from './ActivityForm'

const PAGE_SIZE = 20

const TYPE_OPTIONS = [
  { value: 'CALL', label: '전화' },
  { value: 'MEETING', label: '미팅' },
  { value: 'SITE_VISIT', label: '현장방문' },
  { value: 'EMAIL', label: '이메일' },
  { value: 'ISSUE', label: '이슈' },
  { value: 'KAKAO', label: '카카오' },
]

const RETENTION_OPTIONS = [
  { value: 'AWARENESS', label: '인지' },
  { value: 'INTEREST', label: '관심' },
  { value: 'REVIEW', label: '검토' },
  { value: 'DECISION', label: '구매결정' },
  { value: 'ONBOARDING', label: '온보딩' },
  { value: 'UTILIZATION', label: '활용' },
  { value: 'RENEWAL', label: '재계약' },
  { value: 'EXPANSION', label: '확장' },
]

export function HistoriesPage() {
  const { data: users = [] } = useUserOptions()

  const [search, setSearch] = useState('')
  const [activityType, setActivityType] = useState('')
  const [createdBy, setCreatedBy] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [retention, setRetention] = useState('')
  const [page, setPage] = useState(1)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)

  const params = useMemo(() => {
    const p: Record<string, string | number> = { page, page_size: PAGE_SIZE }
    if (activityType) p.activity_type = activityType
    if (createdBy) p.created_by = createdBy
    if (dateFrom) p.date_from = dateFrom
    if (dateTo) p.date_to = dateTo
    if (retention) p.retention_stage = retention
    return p
  }, [activityType, createdBy, dateFrom, dateTo, retention, page])

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['histories', params],
    queryFn: async () => {
      const { data } = await api.get<ActivityHistory[] | Paginated<ActivityHistory>>(
        '/histories',
        { params },
      )
      return unwrapList(data)
    },
  })

  // 고객사 검색 — 서버 파라미터 없음 → 현재 페이지 내 클라이언트 필터
  const rows = useMemo(() => {
    const items = data?.items ?? []
    if (!search.trim()) return items
    const keyword = search.trim().toLowerCase()
    return items.filter((h) =>
      (h.client_name ?? '').toLowerCase().includes(keyword) ||
      (h.title ?? '').toLowerCase().includes(keyword),
    )
  }, [data?.items, search])
  const total = search.trim() ? rows.length : (data?.total ?? 0)

  const resetPage = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v)
    setPage(1)
  }

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="영업 활동 이력"
        subtitle="컨택·활동·이슈 통합 기록 — 부서 공동 관리"
        actions={
          <button
            type="button"
            onClick={() => setFormOpen(true)}
            className="hidden items-center gap-1.5 rounded-lg bg-slate-800 px-3.5 py-2 text-sm font-semibold text-white hover:bg-slate-700 sm:flex"
          >
            <Plus size={16} weight="bold" />
            이력 등록
          </button>
        }
      />

      <FilterBar>
        <FilterSearch
          value={search}
          onChange={resetPage(setSearch)}
          placeholder="고객사 검색"
          className="min-w-[160px]"
        />
        <FilterSelect
          label="유형"
          value={activityType}
          onChange={resetPage(setActivityType)}
          options={TYPE_OPTIONS}
        />
        <FilterSelect
          label="작성자"
          value={createdBy}
          onChange={resetPage(setCreatedBy)}
          options={users.map((u) => ({ value: u.user_id, label: u.name }))}
        />
        <label className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-slate-500">기간</span>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => resetPage(setDateFrom)(e.target.value)}
            className="h-9 rounded-lg border border-slate-200 px-2 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
            aria-label="시작일"
          />
          <span className="text-slate-300">~</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => resetPage(setDateTo)(e.target.value)}
            className="h-9 rounded-lg border border-slate-200 px-2 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
            aria-label="종료일"
          />
        </label>
        <FilterSelect
          label="리텐션"
          value={retention}
          onChange={resetPage(setRetention)}
          options={RETENTION_OPTIONS}
        />
      </FilterBar>

      {isLoading ? (
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <SkeletonTableRows rows={6} />
        </div>
      ) : isError ? (
        <EmptyState
          icon={<ClockCounterClockwise size={36} />}
          title="이력을 불러오지 못했습니다"
          action={
            <button
              type="button"
              onClick={() => refetch()}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              다시 시도
            </button>
          }
        />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={<ClockCounterClockwise size={36} />}
          title="활동 이력이 없습니다"
          description="[이력 등록]으로 첫 활동을 기록해 보세요."
        />
      ) : (
        <>
          {/* 아코디언 테이블 */}
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            {/* 헤더 (데스크톱) */}
            <div className="hidden grid-cols-[150px_1fr_90px_2fr_110px_1fr_32px] gap-3 border-b border-slate-100 bg-slate-50/60 px-4 py-3 text-xs font-semibold tracking-wide text-slate-500 lg:grid">
              <span>일시</span>
              <span>고객사</span>
              <span>유형</span>
              <span>요약</span>
              <span>작성자</span>
              <span>Next Action</span>
              <span />
            </div>
            <ul>
              {rows.map((h) => {
                const isOpen = expanded === h.history_id
                const isAuto = !!h.is_auto
                return (
                  <li key={h.history_id} className="border-b border-slate-50 last:border-b-0">
                    <button
                      type="button"
                      onClick={() => setExpanded(isOpen ? null : h.history_id)}
                      className="grid w-full grid-cols-[1fr_auto] items-center gap-2 px-4 py-3 text-left hover:bg-slate-50/70 lg:grid-cols-[150px_1fr_90px_2fr_110px_1fr_32px] lg:gap-3"
                      aria-expanded={isOpen}
                    >
                      {/* 모바일: 2줄 요약 / 데스크톱: 그리드 셀 */}
                      <span className="min-w-0 lg:contents">
                        <span className="block text-xs text-slate-400 lg:text-sm lg:text-slate-500">
                          {fmtDateTime(h.activity_date)}
                        </span>
                        <span className="block truncate text-sm font-semibold text-slate-800">
                          {h.client_name ?? (h.client_id ? '고객사' : '미지정 고객')}
                        </span>
                        <span className="mt-0.5 flex items-center gap-1.5 lg:mt-0">
                          <StatusBadge domain="activity" value={h.activity_type} />
                          {isAuto && (
                            <span className="inline-flex rounded bg-slate-100 px-1 py-0.5 text-[10px] font-medium text-slate-500">
                              자동
                            </span>
                          )}
                        </span>
                        <span className="block truncate text-sm text-slate-600">{h.title}</span>
                        <span className="hidden truncate text-sm text-slate-500 lg:block">
                          {h.created_by_name ?? h.manager_name ?? '—'}
                        </span>
                        <span className="hidden truncate text-xs text-slate-400 lg:block">
                          {h.next_action ?? '—'}
                        </span>
                      </span>
                      <CaretDown
                        size={14}
                        className={`shrink-0 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
                      />
                    </button>
                    {isOpen && (
                      <div className="animate-fade-in space-y-3 border-t border-slate-50 bg-slate-50/50 px-5 py-4">
                        <div className="flex flex-wrap items-center gap-2">
                          {h.retention_stage && (
                            <StatusBadge domain="retention" value={h.retention_stage} />
                          )}
                          {h.activity_type === 'ISSUE' && h.issue_status && (
                            <StatusBadge domain="issue" value={h.issue_status} />
                          )}
                          {h.client_id && (
                            <Link
                              to={`/clients/${h.client_id}`}
                              className="text-xs font-medium text-slate-500 underline-offset-2 hover:underline"
                            >
                              고객사 상세 →
                            </Link>
                          )}
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-slate-400">상세</p>
                          <p className="mt-0.5 text-sm whitespace-pre-wrap text-slate-700">
                            {h.content || '—'}
                          </p>
                        </div>
                        {h.main_needs && (
                          <div>
                            <p className="text-xs font-semibold text-slate-400">주요 니즈</p>
                            <p className="mt-0.5 text-sm text-slate-700">{h.main_needs}</p>
                          </div>
                        )}
                        {h.next_action && (
                          <div>
                            <p className="text-xs font-semibold text-slate-400">Next Action</p>
                            <p className="mt-0.5 text-sm text-slate-700">{h.next_action}</p>
                          </div>
                        )}
                        <AuditLine
                          createdByName={h.created_by_name ?? h.manager_name}
                          createdAt={h.created_at}
                          updatedAt={h.updated_at !== h.created_at ? h.updated_at : undefined}
                          auto={isAuto}
                        />
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
          <Pagination total={total} page={page} pageSize={PAGE_SIZE} onChange={setPage} />
        </>
      )}

      <ActivityForm open={formOpen} onClose={() => setFormOpen(false)} />
    </div>
  )
}
