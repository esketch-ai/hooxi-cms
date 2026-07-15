// SCR-05 영업 활동 이력 — 아코디언 테이블 + 공용 ActivityForm
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CaretDown,
  ClockCounterClockwise,
  DownloadSimple,
  Plus,
  Signature,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { FilterBar, FilterSearch, FilterSelect } from '../../components/FilterBar'
import { Pagination } from '../../components/Pagination'
import { StatusBadge } from '../../components/StatusBadge'
import { AuditLine } from '../../components/AuditLine'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonTableRows } from '../../components/Skeleton'
import { Modal } from '../../components/Modal'
import { SignaturePad } from '../../components/SignaturePad'
import { useToast } from '../../components/Toast'
import { api } from '../../lib/api/client'
import { unwrapList, useCodes, useHistoryDocuments, useUserOptions } from '../../lib/api/queries'
import { usePointerCoarse } from '../../lib/usePointerCoarse'
import { downloadDocument, downloadErrorMessage } from '../../lib/download'
import { fmtDateTime, todayKst } from '../../lib/format'
import type { ActivityHistory, Paginated } from '../../types'
import { ActivityForm } from './ActivityForm'

const PAGE_SIZE = 20

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
  const { options: activityTypeOptions } = useCodes('ACTIVITY_TYPE')
  const isCoarse = usePointerCoarse()

  const [search, setSearch] = useState('')
  const [activityType, setActivityType] = useState('')
  const [createdBy, setCreatedBy] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [retention, setRetention] = useState('')
  const [page, setPage] = useState(1)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [signTarget, setSignTarget] = useState<ActivityHistory | null>(null)

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
            className="hidden items-center gap-1.5 rounded-full bg-primary px-3.5 py-2 text-sm font-medium text-on-primary hover:opacity-90 sm:flex"
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
          options={activityTypeOptions}
        />
        <FilterSelect
          label="작성자"
          value={createdBy}
          onChange={resetPage(setCreatedBy)}
          options={users.map((u) => ({ value: u.user_id, label: u.name }))}
        />
        <label className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-ash">기간</span>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => resetPage(setDateFrom)(e.target.value)}
            className="h-9 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
            aria-label="시작일"
          />
          <span className="text-slatey">~</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => resetPage(setDateTo)(e.target.value)}
            className="h-9 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
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
        <div className="rounded-3xl border border-hairline bg-graphite p-5">
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
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
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
          <div className="overflow-hidden rounded-3xl border border-hairline bg-graphite">
            {/* 헤더 (데스크톱) */}
            <div className="hidden grid-cols-[150px_1fr_90px_2fr_110px_1fr_32px] gap-3 border-b border-hairline bg-elevate px-4 py-3 text-xs font-semibold tracking-wide text-ash lg:grid">
              <span>일시</span>
              <span>고객사</span>
              <span>유형</span>
              <span>요약</span>
              <span>작성자</span>
              <span>다음 액션</span>
              <span />
            </div>
            <ul>
              {rows.map((h) => {
                const isOpen = expanded === h.history_id
                const isAuto = !!h.is_auto
                return (
                  <li key={h.history_id} className="border-b border-hairline last:border-b-0">
                    <button
                      type="button"
                      onClick={() => setExpanded(isOpen ? null : h.history_id)}
                      className="grid w-full grid-cols-[1fr_auto] items-center gap-2 px-4 py-3 text-left hover:bg-elevate lg:grid-cols-[150px_1fr_90px_2fr_110px_1fr_32px] lg:gap-3"
                      aria-expanded={isOpen}
                    >
                      {/* 모바일: 2줄 요약 / 데스크톱: 그리드 셀 */}
                      <span className="min-w-0 lg:contents">
                        <span className="block text-xs text-slatey lg:text-sm lg:text-ash">
                          {fmtDateTime(h.activity_date)}
                        </span>
                        <span className="block truncate text-sm font-semibold text-bone">
                          {h.client_name ?? (h.client_id ? '고객사' : '미지정 고객')}
                        </span>
                        <span className="mt-0.5 flex items-center gap-1.5 lg:mt-0">
                          <StatusBadge domain="activity" value={h.activity_type} />
                          {isAuto && (
                            <span className="inline-flex rounded bg-elevate-strong px-1 py-0.5 text-[10px] font-medium text-ash">
                              자동
                            </span>
                          )}
                        </span>
                        <span className="block truncate text-sm text-ash">{h.title}</span>
                        <span className="hidden truncate text-sm text-ash lg:block">
                          {h.created_by_name ?? h.manager_name ?? '—'}
                        </span>
                        <span className="hidden truncate text-xs text-slatey lg:block">
                          {h.next_action ?? '—'}
                        </span>
                      </span>
                      <CaretDown
                        size={14}
                        className={`shrink-0 text-slatey transition-transform ${isOpen ? 'rotate-180' : ''}`}
                      />
                    </button>
                    {isOpen && (
                      <div className="animate-fade-in space-y-3 border-t border-hairline bg-elevate px-5 py-4">
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
                              className="text-xs font-medium text-ash underline-offset-2 hover:underline"
                            >
                              고객사 상세 →
                            </Link>
                          )}
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-slatey">상세</p>
                          <p className="mt-0.5 text-sm whitespace-pre-wrap text-bone">
                            {h.content || '—'}
                          </p>
                        </div>
                        {h.main_needs && (
                          <div>
                            <p className="text-xs font-semibold text-slatey">주요 니즈</p>
                            <p className="mt-0.5 text-sm text-bone">{h.main_needs}</p>
                          </div>
                        )}
                        {h.next_action && (
                          <div>
                            <p className="text-xs font-semibold text-slatey">다음 액션</p>
                            <p className="mt-0.5 text-sm text-bone">{h.next_action}</p>
                          </div>
                        )}
                        <HistoryAttachments historyId={h.history_id} />
                        {/* 태블릿 현장 전용 — 고객 확인 서명 (재서명 허용) */}
                        {isCoarse && (
                          <button
                            type="button"
                            onClick={() => setSignTarget(h)}
                            className="flex items-center gap-1.5 rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate-strong"
                          >
                            <Signature size={16} />
                            고객 확인 서명
                          </button>
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
      <SignatureModal history={signTarget} onClose={() => setSignTarget(null)} />
    </div>
  )
}

/** 서명 제목 규약: 확인서명_{활동일 또는 오늘 KST YYYY-MM-DD} */
function signTitle(history: ActivityHistory): string {
  const dateLabel = (history.activity_date ?? '').slice(0, 10) || todayKst()
  return `확인서명_${dateLabel}`
}

/** 고객 확인 서명 모달 — SignaturePad PNG를 문서함(SIGN)에 업로드, 이력에 연결 */
function SignatureModal({
  history,
  onClose,
}: {
  /** 대상 활동 이력 — null이면 닫힘 */
  history: ActivityHistory | null
  onClose: () => void
}) {
  const { showToast } = useToast()
  const queryClient = useQueryClient()

  const upload = useMutation({
    mutationFn: async (blob: Blob) => {
      if (!history) return
      const title = signTitle(history)
      const form = new FormData()
      form.append('file', new File([blob], `${title}.png`, { type: 'image/png' }))
      form.append('title', title)
      form.append('doc_type', 'SIGN')
      if (history.client_id) form.append('client_id', history.client_id)
      form.append('history_id', history.history_id)
      const { data } = await api.post('/documents', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60_000,
      })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })

  const handleSave = async (blob: Blob) => {
    try {
      await upload.mutateAsync(blob)
      showToast('확인 서명이 첨부되었습니다.', 'success')
      onClose()
    } catch {
      showToast('서명 업로드에 실패했습니다.', 'danger')
    }
  }

  return (
    <Modal open={history != null} onClose={onClose} title="고객 확인 서명" size="md">
      <div className="space-y-3">
        {history && (
          <p className="text-xs text-slatey">
            {history.client_name ?? '미지정 고객'} 활동 이력에{' '}
            <span className="font-mono text-ash">{signTitle(history)}</span>
            으로 첨부됩니다.
          </p>
        )}
        <SignaturePad
          onSave={handleSave}
          onCancel={onClose}
          disabled={upload.isPending}
          saveLabel="서명 저장"
        />
      </div>
    </Modal>
  )
}

/** 확장 행의 현장 첨부(사진·서명) 목록 — 확장된 행에서만 마운트되어 조회 */
function HistoryAttachments({ historyId }: { historyId: string }) {
  const { showToast } = useToast()
  const { data: docs = [] } = useHistoryDocuments(historyId)

  if (docs.length === 0) return null

  const handleDownload = async (docId: string, title?: string) => {
    try {
      await downloadDocument(docId, title)
    } catch (err) {
      showToast(downloadErrorMessage(err), 'danger')
    }
  }

  return (
    <div>
      <p className="text-xs font-semibold text-slatey">현장 첨부</p>
      <ul className="mt-1 space-y-1">
        {docs.map((d) => (
          <li key={d.doc_id} className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => void handleDownload(d.doc_id, d.title)}
              className="flex min-w-0 items-center gap-1.5 text-sm text-bone underline-offset-2 hover:underline"
            >
              <DownloadSimple size={14} className="shrink-0 text-smoke" />
              <span className="truncate">{d.title}</span>
            </button>
            {d.doc_type === 'SIGN' && (
              <span className="inline-flex shrink-0 rounded bg-elevate-strong px-1 py-0.5 text-[10px] font-medium text-ash">
                서명
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
