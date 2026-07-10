// SCR-08 좌측 스레드 리스트 — 검색 + pill 필터(전체/직원 연결/AI 응대) + 스레드 아이템
import { ChatCircleDots, MagnifyingGlass } from '@phosphor-icons/react'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonTableRows } from '../../components/Skeleton'
import { elapsedServer } from '../../lib/format'
import type { ChatThread } from '../../types'
import { ThreadModePill, ThreadWaitingBadge } from './ThreadBadges'

export type ThreadFilter = 'ALL' | 'HUMAN' | 'AI'

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
    HUMAN: threads.filter((t) => t.mode === 'HUMAN').length,
    AI: threads.filter((t) => t.mode === 'AI').length,
  }
  const filtered = filter === 'ALL' ? threads : threads.filter((t) => t.mode === filter)

  const PILLS: { key: ThreadFilter; label: string }[] = [
    { key: 'ALL', label: `전체 (${counts.ALL})` },
    { key: 'HUMAN', label: `직원 연결 (${counts.HUMAN})` },
    { key: 'AI', label: `AI 응대 (${counts.AI})` },
  ]

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* 검색 + pill 필터 */}
      <div className="shrink-0 border-b border-slate-200 bg-white p-4">
        <div className="relative mb-3 w-full">
          <MagnifyingGlass
            size={15}
            className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-slate-400"
          />
          <input
            type="search"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="고객사명, 대화 내용 검색..."
            className="w-full rounded-md border border-transparent bg-slate-100 py-2 pr-4 pl-9 text-sm outline-none transition-colors focus:border-slate-300 focus:bg-white focus:ring-2 focus:ring-slate-200"
            aria-label="상담 검색"
          />
        </div>
        <div className="flex gap-2">
          {PILLS.map((pill) => (
            <button
              key={pill.key}
              type="button"
              onClick={() => onFilterChange(pill.key)}
              className={`rounded-full px-3 py-1 text-xs font-medium whitespace-nowrap transition-colors ${
                filter === pill.key
                  ? 'bg-slate-800 text-white'
                  : 'border border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
              }`}
            >
              {pill.label}
            </button>
          ))}
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
                className={`relative block w-full border-b border-slate-100 p-4 text-left transition-colors ${
                  active ? 'bg-white' : 'hover:bg-slate-100/50'
                }`}
              >
                {active && <span className="absolute top-0 bottom-0 left-0 w-1 bg-slate-800" />}
                <div className="mb-1 flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-sm font-bold text-slate-900">
                      {threadTitle(thread)}
                    </span>
                    <ThreadWaitingBadge thread={thread} />
                  </div>
                  <span className="shrink-0 text-xs text-slate-400">
                    {elapsedServer(thread.last_message_at)}
                  </span>
                </div>
                <p className="mb-2 truncate text-sm text-slate-500">
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
