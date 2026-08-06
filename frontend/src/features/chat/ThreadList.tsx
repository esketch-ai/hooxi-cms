// SCR-08 좌측 상담 목록 — 검색 + pill 필터 + [신규 문의(미매핑) 섹션] + 고객사별 그룹(접기) → 개별고객 → 스레드
import { useMemo, useState } from 'react'
import {
  Buildings,
  CaretDown,
  CaretRight,
  ChatCircleDots,
  MagnifyingGlass,
  Sparkle,
  User,
} from '@phosphor-icons/react'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonTableRows } from '../../components/Skeleton'
import { elapsedServer } from '../../lib/format'
import type { ChatThread, KakaoContact } from '../../types'
import { ThreadModePill, ThreadWaitingBadge } from './ThreadBadges'
import { PendingContacts } from './PendingContacts'

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
  /** 신규 문의(미매핑) — PENDING 연락처 */
  pendingContacts: KakaoContact[]
  pendingLoading: boolean
}

/** 스레드 표시명: 고객사명 → 연락처명 → 미승인 (ChatRoom 헤더 등 공용) */
export function threadTitle(thread: ChatThread): string {
  return thread.client_name ?? thread.contact_name ?? '미승인 고객'
}

const NO_CLIENT = '__none__'

export function ThreadList({
  threads,
  isLoading,
  search,
  onSearchChange,
  filter,
  onFilterChange,
  selectedId,
  onSelect,
  pendingContacts,
  pendingLoading,
}: ThreadListProps) {
  const counts = {
    ALL: threads.length,
    WAITING: threads.filter((t) => t.status === 'WAITING').length,
    HUMAN: threads.filter((t) => t.mode === 'HUMAN').length,
    AI: threads.filter((t) => t.mode === 'AI').length,
  }
  const matched = useMemo(
    () =>
      filter === 'ALL'
        ? threads
        : filter === 'WAITING'
          ? threads.filter((t) => t.status === 'WAITING')
          : threads.filter((t) => t.mode === filter),
    [threads, filter],
  )

  // 고객사 → 개별고객(연락처) → 스레드로 2단 그룹핑. 대기(WAITING) 있는 고객사를 상단에.
  const groups = useMemo(() => {
    const byClient = new Map<
      string,
      { key: string; clientName: string; threads: ChatThread[] }
    >()
    for (const t of matched) {
      const key = t.client_id ?? NO_CLIENT
      if (!byClient.has(key)) {
        byClient.set(key, {
          key,
          clientName: t.client_name ?? '고객사 미지정',
          threads: [],
        })
      }
      byClient.get(key)!.threads.push(t)
    }
    const out = [...byClient.values()].map((g) => {
      const byContact = new Map<
        string,
        { key: string; contactName: string; threads: ChatThread[] }
      >()
      for (const t of g.threads) {
        const ck = t.kakao_contact_id ?? NO_CLIENT
        if (!byContact.has(ck)) {
          byContact.set(ck, { key: ck, contactName: t.contact_name ?? '이름 미상', threads: [] })
        }
        byContact.get(ck)!.threads.push(t)
      }
      return {
        ...g,
        contacts: [...byContact.values()],
        waiting: g.threads.filter((t) => t.status === 'WAITING').length,
      }
    })
    // 대기 있는 고객사를 위로 (입력이 last_message_at 역순이라 그 외 순서는 보존)
    return out.sort((a, b) => Number(b.waiting > 0) - Number(a.waiting > 0))
  }, [matched])

  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const toggle = (key: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  const [pendingOpen, setPendingOpen] = useState(true)

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
            placeholder="고객사명, 연락처명 검색..."
            className="w-full rounded-md border border-hairline bg-graphite-2 py-2 pr-4 pl-9 text-sm text-bone outline-none transition-colors placeholder:text-slatey focus:border-white/30 focus:bg-graphite focus:ring-2 focus:ring-hairline"
            aria-label="상담 검색"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {PILLS.map((pill) => {
            const urgent = pill.key === 'WAITING' && counts.WAITING > 0
            const active = filter === pill.key
            return (
              <button
                key={pill.key}
                type="button"
                onClick={() => onFilterChange(pill.key)}
                className={`rounded-full px-3 py-1 text-xs font-medium whitespace-nowrap transition-colors ${
                  active
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

      {/* 목록 (신규 문의 섹션 + 고객사 그룹) */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {/* 신규 문의(미매핑) — PENDING 연락처 */}
        {pendingContacts.length > 0 && (
          <div className="border-b-2 border-amber-400/30">
            <button
              type="button"
              onClick={() => setPendingOpen((v) => !v)}
              className="flex w-full items-center gap-2 bg-amber-500/10 px-4 py-2.5 text-left text-xs font-bold text-amber-700 dark:text-amber-300"
            >
              {pendingOpen ? <CaretDown size={13} /> : <CaretRight size={13} />}
              <Sparkle size={14} weight="fill" />
              신규 문의 (미매핑)
              <span className="ml-auto inline-flex min-w-[18px] items-center justify-center rounded-full bg-rose-500 px-1.5 py-px text-[10px] font-bold text-white">
                {pendingContacts.length}
              </span>
            </button>
            {pendingOpen && (
              <PendingContacts contacts={pendingContacts} isLoading={pendingLoading} embedded />
            )}
          </div>
        )}

        {/* 고객사 그룹 트리 */}
        {isLoading ? (
          <div className="p-4">
            <SkeletonTableRows rows={5} />
          </div>
        ) : groups.length === 0 ? (
          pendingContacts.length === 0 && (
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
          )
        ) : (
          groups.map((g) => {
            const open = !collapsed.has(g.key)
            return (
              <div key={g.key} className="border-b border-hairline">
                {/* 고객사 헤더 (접기/펼치기) */}
                <button
                  type="button"
                  onClick={() => toggle(g.key)}
                  className="flex w-full items-center gap-2 bg-graphite/60 px-4 py-2 text-left hover:bg-elevate"
                >
                  {open ? <CaretDown size={13} className="text-slatey" /> : <CaretRight size={13} className="text-slatey" />}
                  <Buildings size={15} className="text-smoke" />
                  <span className="truncate text-sm font-bold text-bone">{g.clientName}</span>
                  <span className="ml-auto flex items-center gap-1.5 text-[11px] text-slatey">
                    상담 {g.threads.length}
                    {g.waiting > 0 && (
                      <span className="inline-flex items-center rounded-full bg-rose-500/15 px-1.5 py-px font-bold text-rose-700 dark:text-rose-300">
                        대기 {g.waiting}
                      </span>
                    )}
                  </span>
                </button>

                {/* 개별 고객(연락처) → 스레드 */}
                {open &&
                  g.contacts.map((c) => (
                    <div key={c.key}>
                      <div className="flex items-center gap-1.5 px-4 py-1.5 pl-8 text-xs text-slatey">
                        <User size={13} />
                        <span className="truncate font-medium text-ash">{c.contactName}</span>
                        <span className="ml-auto">{c.threads.length}</span>
                      </div>
                      {c.threads.map((thread) => {
                        const activeThread = thread.thread_id === selectedId
                        return (
                          <button
                            key={thread.thread_id}
                            type="button"
                            onClick={() => onSelect(thread.thread_id)}
                            className={`relative block w-full border-t border-hairline/50 py-2.5 pr-4 pl-10 text-left transition-colors ${
                              activeThread ? 'bg-graphite' : 'hover:bg-elevate'
                            }`}
                          >
                            {activeThread && (
                              <span className="absolute top-0 bottom-0 left-0 w-1 bg-primary" />
                            )}
                            <div className="mb-1 flex items-start justify-between gap-2">
                              <div className="flex min-w-0 items-center gap-1.5">
                                <ThreadWaitingBadge thread={thread} />
                                <span className="truncate text-sm text-ash">
                                  {thread.last_message_preview ?? '메시지가 없습니다'}
                                </span>
                              </div>
                              <span className="shrink-0 text-[11px] text-slatey">
                                {elapsedServer(thread.last_message_at)}
                              </span>
                            </div>
                            <ThreadModePill thread={thread} />
                          </button>
                        )
                      })}
                    </div>
                  ))}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
