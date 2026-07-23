// SCR-08 좌측 스레드 리스트 — 검색 + pill 필터(전체/연결 대기/직원 상담/AI 응대) + 스레드 아이템
import { ChatCircleDots, MagnifyingGlass } from '@phosphor-icons/react'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonTableRows } from '../../components/Skeleton'
import { elapsedServer } from '../../lib/format'
import type { ChatThread } from '../../types'
import { ThreadModePill, ThreadWaitingBadge } from './ThreadBadges'

export type ThreadFilter = 'ALL' | 'WAITING' | 'HUMAN' | 'AI'

interface ThreadListProps {
  threads: ChatThread[]
  isLoading: boolean
  search: string
  onSearchChange: (value: string) => void
  filter: ThreadFilter
  onFilterChange: (value: ThreadFilter) => void
  selectedId: string | null
  onSelect: (threadId: string) => void
}

/** 스레드 표시명: 고객사명 → 연락처명 → 미지정 */
export function threadTitle(thread: ChatThread): string {
  return thread.client_name ?? thread.contact_name ?? '미승인 고객'
}

export function ThreadList({
  threads,
  isLoading,
  search,
  onSearchChange,
  filter,
  onFilterChange,
  selectedId,
  onSelect,
}: ThreadListProps) {
  const counts = {
    ALL: threads.length,
    WAITING: threads.filter((t) => t.status === 'WAITING').length,
    HUMAN: threads.filter((t) => t.mode === 'HUMAN').length,
    AI: threads.filter((t) => t.mode === 'AI').length,
  }
  const matched =
    filter === 'ALL'
      ? threads
      : filter === 'WAITING'
        ? threads.filter((t) => t.status === 'WAITING')
        : threads.filter((t) => t.mode === filter)
  // 연결 대기(WAITING)는 즉시 상담원이 붙어야 할 건 — 어느 필터에서든 항상 상단 고정.
  // 입력이 last_message_at 역순으로 정렬돼 있고 Array.sort는 안정적이라 순서가 보존된다.
  const filtered = [...matched].sort(
    (a, b) => Number(b.status === 'WAITING') - Number(a.status === 'WAITING'),
  )

  const PILLS: { key: ThreadFilter; label: string }[] = [
    { key: 'ALL', label: `전체 (${counts.ALL})` },
    { key: 'WAITING', label: `연결 대기 (${counts.WAITING})` },
    { key: 'HUMAN', label: `직원 상담 (${counts.HUMAN})` },
    { key: 'AI', label: `AI 응대 (${counts.AI})` },
  ]

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* 검색 + pill 필터 */}
      <div className="shrink-0 border-b border-hairline bg-graphite p-4">
        <div className="relative mb-3 w-full">
          <MagnifyingGlass
            size={15}
            className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-slatey"
          />
          <input
            type="search"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="고객사명, 대화 내용 검색..."
            className="w-full rounded-md border border-hairline bg-graphite-2 py-2 pr-4 pl-9 text-sm text-bone outline-none transition-colors placeholder:text-slatey focus:border-white/30 focus:bg-graphite focus:ring-2 focus:ring-hairline"
            aria-label="상담 검색"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {PILLS.map((pill) => {
            // 대기 건이 있는데 지금 그 필터가 아니면 rose로 강조 — '지금 붙어야 할 건'을 부각
            const urgent = pill.key === 'WAITING' && counts.WAITING > 0
            const selected = filter === pill.key
            return (
              <button
                key={pill.key}
                type="button"
                onClick={() => onFilterChange(pill.key)}
                className={`rounded-full px-3 py-1 text-xs font-medium whitespace-nowrap transition-colors ${
                  selected
                    ? 'bg-primary text-on-primary'
                    : urgent
                      ? 'border border-rose-400/40 bg-rose-500/15 text-rose-700 hover:bg-rose-500/25 dark:text-rose-300'
                      : 'border border-hairline bg-graphite text-ash hover:bg-elevate'
                }`}
              >
                {pill.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* 스레드 아이템 목록 */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="p-4">
            <SkeletonTableRows rows={5} />
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<ChatCircleDots size={32} />}
            title={search ? '검색 결과가 없습니다' : '상담 스레드가 없습니다'}
            description={
              search
                ? '다른 검색어로 다시 시도해 보세요.'
                : '카카오 채널로 문의가 접수되면 이곳에 표시됩니다.'
            }
            className="m-4 py-10"
          />
        ) : (
          filtered.map((thread) => {
            const active = thread.thread_id === selectedId
            return (
              <button
                key={thread.thread_id}
                type="button"
                onClick={() => onSelect(thread.thread_id)}
                className={`relative block w-full border-b border-hairline p-4 text-left transition-colors ${
                  active ? 'bg-graphite' : 'hover:bg-elevate'
                }`}
              >
                {active && <span className="absolute top-0 bottom-0 left-0 w-1 bg-primary" />}
                <div className="mb-1 flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-sm font-bold text-bone">
                      {threadTitle(thread)}
                    </span>
                    <ThreadWaitingBadge thread={thread} />
                  </div>
                  <span className="shrink-0 text-xs text-slatey">
                    {elapsedServer(thread.last_message_at)}
                  </span>
                </div>
                <p className="mb-2 truncate text-sm text-ash">
                  {thread.last_message_preview ?? '메시지가 없습니다'}
                </p>
                <div className="flex items-center gap-1">
                  <ThreadModePill thread={thread} />
                </div>
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}
