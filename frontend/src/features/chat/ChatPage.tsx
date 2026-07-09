// SCR-08 카카오톡 상담 관제 /chat — 2단 레이아웃(스레드 리스트 + 대화창), 5초 폴링
// 모바일: 리스트↔대화창 전환(선택 시 대화창 풀스크린) · ?client= 딥링크 수신
import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChatCircleDots } from '@phosphor-icons/react'
import { useToast } from '../../components/Toast'
import { useChatThreads, usePendingContacts } from './api'
import { ChatRoom } from './ChatRoom'
import { PendingContacts } from './PendingContacts'
import { ThreadList, type ThreadFilter } from './ThreadList'

type ListTab = 'threads' | 'pending'

/** 300ms 디바운스 값 */
function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

export function ChatPage() {
  const [searchParams] = useSearchParams()
  const clientParam = searchParams.get('client')
  const { showToast } = useToast()

  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [filter, setFilter] = useState<ThreadFilter>('ALL')
  const [tab, setTab] = useState<ListTab>('threads')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const { data: threads = [], isLoading } = useChatThreads(debouncedSearch)
  const { data: pendingContacts = [], isLoading: pendingLoading } = usePendingContacts()

  // ?client=<id> 딥링크 — 해당 고객사 최신 스레드 자동 선택 (1회)
  const appliedClientRef = useRef<string | null>(null)
  useEffect(() => {
    if (!clientParam || threads.length === 0) return
    if (appliedClientRef.current === clientParam) return
    appliedClientRef.current = clientParam
    const target = threads.find((t) => t.client_id === clientParam)
    if (target) {
      setSelectedId(target.thread_id)
    } else {
      showToast('해당 고객사의 상담 스레드가 아직 없습니다.', 'info')
    }
  }, [clientParam, threads, showToast])

  const selected = useMemo(
    () => threads.find((t) => t.thread_id === selectedId) ?? null,
    [threads, selectedId],
  )

  const TABS: { key: ListTab; label: string }[] = [
    { key: 'threads', label: '상담' },
    {
      key: 'pending',
      label: `승인 대기${pendingContacts.length > 0 ? ` (${pendingContacts.length})` : ''}`,
    },
  ]

  return (
    <div className="animate-fade-in -mx-4 -mt-5 -mb-24 flex h-[calc(100dvh-4rem-3.75rem)] overflow-hidden bg-white lg:-mx-6 lg:-mb-6 lg:h-[calc(100dvh-4rem)]">
      {/* 좌측: 스레드 리스트 / 승인 대기 큐 */}
      <div
        className={`w-full flex-col border-r border-slate-200 bg-slate-50 md:flex md:w-80 lg:w-96 ${
          selected ? 'hidden' : 'flex'
        }`}
      >
        {/* 상담 / 승인 대기 탭 */}
        <div className="flex shrink-0 border-b border-slate-200 bg-white">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`flex-1 border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
                tab === t.key
                  ? 'border-slate-800 text-slate-900'
                  : 'border-transparent text-slate-400 hover:text-slate-600'
              }`}
            >
              {t.label}
              {t.key === 'pending' && pendingContacts.length > 0 && (
                <span className="ml-1.5 inline-flex min-w-[16px] items-center justify-center rounded-full bg-rose-500 px-1 py-px align-middle text-[9px] font-bold text-white">
                  {pendingContacts.length}
                </span>
              )}
            </button>
          ))}
        </div>

        {tab === 'threads' ? (
          <ThreadList
            threads={threads}
            isLoading={isLoading}
            search={search}
            onSearchChange={setSearch}
            filter={filter}
            onFilterChange={setFilter}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        ) : (
          <PendingContacts contacts={pendingContacts} isLoading={pendingLoading} />
        )}
      </div>

      {/* 우측: 대화창 (모바일은 선택 시 풀스크린) */}
      <div className={`min-w-0 flex-1 md:flex ${selected ? 'flex' : 'hidden'}`}>
        {selected ? (
          <ChatRoom thread={selected} onBack={() => setSelectedId(null)} />
        ) : (
          <div className="flex min-w-0 flex-1 flex-col items-center justify-center gap-2 bg-[#f5f5f5] text-slate-400">
            <ChatCircleDots size={40} />
            <p className="text-sm font-medium">좌측 목록에서 상담을 선택하세요</p>
            <p className="text-xs">고객 카카오톡 문의가 5초 간격으로 자동 갱신됩니다.</p>
          </div>
        )}
      </div>
    </div>
  )
}
