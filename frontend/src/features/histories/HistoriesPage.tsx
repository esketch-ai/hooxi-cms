// SCR-05 영업 활동 이력 — 날짜 그룹 아코디언 테이블 + 공용 ActivityForm
import { Fragment, useMemo, useState } from 'react'
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
import { DocumentPreviewModal } from '../../components/DocumentPreviewModal'
import { useToast } from '../../components/Toast'
import { api } from '../../lib/api/client'
import {
  unwrapList,
  useClientOptions,
  useCodes,
  useHistoryDocuments,
  useUserOptions,
} from '../../lib/api/queries'
import { usePointerCoarse } from '../../lib/usePointerCoarse'
import { useDebounced } from '../../lib/useDebounced'
import { downloadDocument, downloadErrorMessage, previewKind } from '../../lib/download'
import { fmtDayLabel, fmtTime, todayKst } from '../../lib/format'
import type { ActivityHistory, Document, Paginated } from '../../types'
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
  const debouncedSearch = useDebounced(search)
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
    if (debouncedSearch.trim()) p.search = debouncedSearch.trim()
    if (activityType) p.activity_type = activityType
    if (createdBy) p.created_by = createdBy
    if (dateFrom) p.date_from = dateFrom
    if (dateTo) p.date_to = dateTo
    if (retention) p.retention_stage = retention
    return p
  }, [debouncedSearch, activityType, createdBy, dateFrom, dateTo, retention, page])

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

  const rows = data?.items ?? []
  const total = data?.total ?? 0

  // 날짜 그룹 — activity_date(사용자 입력 벽시계)의 YYYY-MM-DD 기준.
  // 백엔드가 activity_date desc 정렬이므로 순회 중 날짜가 바뀔 때마다 새 그룹.
  const groups = useMemo(() => {
    const out: { date: string; items: ActivityHistory[] }[] = []
    for (const h of rows) {
      const date = (h.activity_date ?? '').slice(0, 10)
      const last = out[out.length - 1]
      if (last && last.date === date) last.items.push(h)
      else out.push({ date, items: [h] })
    }
    return out
  }, [rows])

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
          placeholder="고객사·제목 검색"
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
            {/* 헤더 (데스크톱) — 시간 · 유형 · 활동(고객사+제목) · 작성자 · 캐럿 */}
            <div className="hidden grid-cols-[48px_88px_1fr_110px_32px] gap-3 border-b border-hairline bg-elevate px-4 py-3 text-xs font-semibold tracking-wide text-ash lg:grid">
              <span>시간</span>
              <span>유형</span>
              <span>활동</span>
              <span>작성자</span>
              <span />
            </div>
            <ul>
              {groups.map((g, gi) => (
                <Fragment key={`${g.date}-${gi}`}>
                  {/* 날짜 그룹 헤더 — 모바일·데스크톱 공용 */}
                  <li className="flex items-center gap-2 border-b border-hairline bg-elevate/60 px-4 py-1.5">
                    <span className="text-xs font-semibold text-ash">{fmtDayLabel(g.date)}</span>
                    <span className="ml-auto rounded-full bg-elevate-strong px-1.5 py-0.5 text-[10px] font-bold text-ash">
                      {g.items.length}건
                    </span>
                  </li>
                  {g.items.map((h) => {
                const isOpen = expanded === h.history_id
                const isAuto = !!h.is_auto
                const isIssue = h.activity_type === 'ISSUE'
                return (
                  <li key={h.history_id} className="border-b border-hairline last:border-b-0">
                    <button
                      type="button"
                      onClick={() => setExpanded(isOpen ? null : h.history_id)}
                      className="grid w-full grid-cols-[1fr_auto] items-center gap-2 px-4 py-1.5 text-left hover:bg-elevate lg:grid-cols-[48px_88px_1fr_110px_32px] lg:gap-3"
                      aria-expanded={isOpen}
                    >
                      {/* 모바일: 2줄(시간·칩·고객사 / 제목) / 데스크톱: 그리드 셀 */}
                      <span className="min-w-0 lg:contents">
                        <span className="flex items-center gap-1.5 lg:contents">
                          <span className="shrink-0 text-xs text-slatey lg:text-sm lg:text-ash">
                            {fmtTime(h.activity_date)}
                          </span>
                          <span className="flex shrink-0 items-center gap-1.5">
                            <StatusBadge domain="activity" value={h.activity_type} />
                            {isAuto && (
                              <span className="inline-flex rounded bg-elevate-strong px-1 py-0.5 text-[10px] font-medium text-ash">
                                자동
                              </span>
                            )}
                          </span>
                          <span className="min-w-0 truncate text-sm font-semibold text-bone lg:hidden">
                            {h.client_name ?? (h.client_id ? '고객사' : '미지정 고객')}
                          </span>
                        </span>
                        {/* 활동 한 줄 — ActionCenter 스캔 문법: 칩 · 고객사 · 제목 · 배지 */}
                        <span className="mt-0.5 flex min-w-0 items-center gap-1.5 lg:mt-0">
                          {isIssue && h.priority === 'URGENT' && (
                            <span className="shrink-0 rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] font-bold text-rose-700 dark:text-rose-300">
                              긴급
                            </span>
                          )}
                          <span className="min-w-0 truncate text-sm">
                            <span className="hidden font-semibold text-bone lg:inline">
                              {h.client_name ?? (h.client_id ? '고객사' : '미지정 고객')}
                              <span className="font-normal text-slatey"> · </span>
                            </span>
                            <span className="text-ash">{h.title}</span>
                          </span>
                          {isIssue && h.issue_status && (
                            <StatusBadge domain="issue" value={h.issue_status} className="shrink-0" />
                          )}
                          {h.next_action && (
                            <span className="hidden max-w-[200px] shrink-0 truncate rounded bg-elevate-strong px-1.5 py-0.5 text-[10px] font-medium text-slatey lg:inline-block">
                              다음: {h.next_action}
                            </span>
                          )}
                        </span>
                        <span className="hidden truncate text-sm text-ash lg:block">
                          {h.created_by_name ?? h.manager_name ?? '—'}
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
                          {h.client_id ? (
                            <Link
                              to={`/clients/${h.client_id}`}
                              className="text-xs font-medium text-ash underline-offset-2 hover:underline"
                            >
                              고객사 상세 →
                            </Link>
                          ) : (
                            <LinkClientControl historyId={h.history_id} />
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
                </Fragment>
              ))}
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

/** 미상 고객 이력의 사후 고객사 연결 (P1-D) — 미연결 건만 허용, 이미 연결된 건 변경은 서버 409 */
function LinkClientControl({ historyId }: { historyId: string }) {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const { data: clients = [] } = useClientOptions()
  const [clientId, setClientId] = useState('')

  const link = useMutation({
    mutationFn: async (targetClientId: string) => {
      const { data } = await api.patch(`/histories/${historyId}/client`, {
        client_id: targetClientId,
      })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['histories'] })
      queryClient.invalidateQueries({ queryKey: ['issues'] })
      queryClient.invalidateQueries({ queryKey: ['clients'] })
    },
  })

  const handleLink = async () => {
    if (!clientId) return
    try {
      await link.mutateAsync(clientId)
      showToast('고객사가 연결되었습니다.', 'success')
    } catch (err) {
      // 409(이미 연결·동시 연결) — 서버 detail 그대로 노출
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      showToast(detail ?? '고객사 연결에 실패했습니다.', 'danger')
    }
  }

  return (
    <span className="flex items-center gap-1.5">
      <select
        value={clientId}
        onChange={(e) => setClientId(e.target.value)}
        className="h-8 rounded-lg border border-hairline bg-graphite px-2 text-xs text-bone focus:border-white/30 focus:outline-none"
        aria-label="연결할 고객사 선택"
      >
        <option value="">고객사 선택…</option>
        {clients.map((c) => (
          <option key={c.client_id} value={c.client_id}>
            {c.company_name}
          </option>
        ))}
      </select>
      <button
        type="button"
        onClick={() => void handleLink()}
        disabled={!clientId || link.isPending}
        className="rounded-full border border-hairline px-2.5 py-1 text-xs font-medium text-bone hover:bg-elevate-strong disabled:opacity-50"
      >
        고객사 연결
      </button>
    </span>
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
  // 제목 클릭 → 미리보기(이미지/PDF만) — 다운로드는 우측 아이콘 버튼으로 분리
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null)

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
            {previewKind(d) ? (
              <button
                type="button"
                onClick={() => setPreviewDoc(d)}
                className="min-w-0 truncate text-sm text-bone underline-offset-2 hover:underline"
                title="미리보기"
              >
                {d.title}
              </button>
            ) : (
              <span className="min-w-0 truncate text-sm text-bone">{d.title}</span>
            )}
            {d.doc_type === 'SIGN' && (
              <span className="inline-flex shrink-0 rounded bg-elevate-strong px-1 py-0.5 text-[10px] font-medium text-ash">
                서명
              </span>
            )}
            <button
              type="button"
              onClick={() => void handleDownload(d.doc_id, d.title)}
              className="shrink-0 rounded p-0.5 text-smoke hover:bg-elevate hover:text-bone"
              title="다운로드"
              aria-label={`${d.title} 다운로드`}
            >
              <DownloadSimple size={14} />
            </button>
          </li>
        ))}
      </ul>
      <DocumentPreviewModal doc={previewDoc} onClose={() => setPreviewDoc(null)} />
    </div>
  )
}
