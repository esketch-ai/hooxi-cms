// SCR-08 우측 대화창 — 헤더(모드 토글·딥링크·종료) / 말풍선 4종 / 입력창 (목업 08_chat.html)
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import { isAxiosError } from 'axios'
import {
  AddressBook,
  ArrowLeft,
  CircleNotch,
  PaperPlaneRight,
  Robot,
  WarningCircle,
} from '@phosphor-icons/react'
import { useAuth } from '../../app/AuthProvider'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { Skeleton } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { BADGE_DICTIONARY } from '../../components/StatusBadge'
import { fmtDate } from '../../lib/format'
import { useClient, useClientAssets } from '../clients/api'
import type { ChatMessage, ChatThread } from '../../types'
import { useChatMessages, useReplyThread, useUpdateThread } from './api'
import { threadTitle } from './ThreadList'

const MAX_LEN = 1000

/** '오후 4:30' */
function fmtKakaoTime(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString('ko-KR', { hour: 'numeric', minute: '2-digit' })
}

/** '2026년 7월 6일 월요일' */
function fmtDateHeading(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  })
}

interface ChatRoomProps {
  thread: ChatThread
  /** 모바일: 리스트로 복귀 */
  onBack: () => void
}

export function ChatRoom({ thread, onBack }: ChatRoomProps) {
  const { user } = useAuth()
  const { showToast } = useToast()
  const { data: messages = [], isLoading } = useChatMessages(thread.thread_id)
  const reply = useReplyThread(thread.thread_id)
  const update = useUpdateThread(thread.thread_id)

  // 컨텍스트 라인(계약 상태 | 자산 요약) — 스레드 조인 필드 우선, 없으면 고객사 조회 폴백
  const { data: client } = useClient(thread.client_id ?? undefined)
  const { data: assets = [] } = useClientAssets(thread.client_id ?? undefined)
  const contractStatus = thread.contract_status ?? client?.contract_status
  const contractLabel = contractStatus
    ? (BADGE_DICTIONARY.contract[contractStatus]?.label ?? contractStatus)
    : null
  const assetSummary =
    thread.asset_summary ?? (assets.length > 0 ? `자산 ${assets.length}종` : null)
  const contextLine = thread.client_id
    ? [contractLabel && `계약 상태: ${contractLabel}`, assetSummary].filter(Boolean).join(' | ')
    : '미승인 고객 — 고객사 미지정 (승인 대기 탭에서 매핑)'

  const closed = thread.status === 'CLOSED'

  // ── 발송 실패(미전달) 로컬 추적 — reply 응답 delivery 기반 ────────────
  const [failedIds, setFailedIds] = useState<Set<string>>(new Set())
  const [failedContents, setFailedContents] = useState<string[]>([])
  const isUndelivered = (m: ChatMessage): boolean =>
    m.sender_type === 'STAFF' &&
    (failedIds.has(m.message_id) ||
      m.delivery_status === 'FAILED' ||
      m.delivery_status === 'NOT_CONFIGURED' ||
      (!!m.content && failedContents.includes(m.content)))

  // ── 입력창 ───────────────────────────────────────────────────────────
  const [text, setText] = useState('')
  const taRef = useRef<HTMLTextAreaElement>(null)
  const autoResize = () => {
    const el = taRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`
  }

  const send = () => {
    const content = text.trim()
    if (!content || content.length > MAX_LEN || reply.isPending || closed) return
    reply.mutate(content, {
      onSuccess: (res) => {
        setText('')
        if (taRef.current) taRef.current.style.height = 'auto'
        if (res.delivery === 'SENT') return
        const failedId = res.message?.message_id ?? res.message_id
        if (failedId) {
          setFailedIds((prev) => new Set(prev).add(failedId))
        } else {
          setFailedContents((prev) => [...prev, content])
        }
        showToast(
          res.delivery === 'NOT_CONFIGURED'
            ? '카카오 발송이 설정되지 않아 고객에게 전달되지 않았습니다. (메시지는 기록됨)'
            : '카카오 발송에 실패했습니다. 고객이 채널 친구인지 확인해 주세요.',
          'danger',
        )
      },
      onError: (err) => {
        if (isAxiosError(err) && err.response?.status === 503) {
          showToast('카카오 발송이 설정되지 않았습니다. 환경 설정을 확인해 주세요.', 'danger')
        } else {
          showToast('메시지 전송에 실패했습니다. 잠시 후 다시 시도해 주세요.', 'danger')
        }
      },
    })
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // 한글 IME 조합 중 Enter 무시
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      send()
    }
  }

  // ── 모드 전환 · 상담 종료 ────────────────────────────────────────────
  const [closeOpen, setCloseOpen] = useState(false)

  const switchMode = (mode: 'AI' | 'HUMAN') => {
    if (mode === thread.mode || update.isPending || closed) return
    update.mutate(
      {
        mode,
        // 직원 개입 시 본인 배정 + WAITING 해제
        ...(mode === 'HUMAN' && user ? { assigned_manager_id: user.user_id } : {}),
        ...(mode === 'HUMAN' && thread.status === 'WAITING' ? { status: 'OPEN' as const } : {}),
      },
      {
        onSuccess: () =>
          showToast(
            mode === 'HUMAN'
              ? '직원 개입 모드로 전환되었습니다.'
              : 'AI 자동 응대 모드로 전환되었습니다.',
            'success',
          ),
        onError: () => showToast('모드 전환에 실패했습니다.', 'danger'),
      },
    )
  }

  const closeThread = () => {
    update.mutate(
      { status: 'CLOSED' },
      {
        onSuccess: () => {
          setCloseOpen(false)
          showToast('상담이 종료되었습니다. 활동 이력(카카오)에 자동 기록됩니다.', 'success')
        },
        onError: () => showToast('상담 종료에 실패했습니다.', 'danger'),
      },
    )
  }

  // ── 새 메시지 도착 시 스크롤 하단 고정 ──────────────────────────────
  const scrollRef = useRef<HTMLDivElement>(null)
  const lastMessageId = messages.length > 0 ? messages[messages.length - 1].message_id : null
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [lastMessageId, thread.thread_id])

  // 날짜 구분선 삽입용 그룹핑
  const grouped = useMemo(() => {
    const out: { dateKey: string; heading: string; items: ChatMessage[] }[] = []
    for (const m of messages) {
      const key = fmtDate(m.created_at)
      const last = out[out.length - 1]
      if (last && last.dateKey === key) last.items.push(m)
      else out.push({ dateKey: key, heading: fmtDateHeading(m.created_at), items: [m] })
    }
    return out
  }, [messages])

  const customerName = thread.contact_name ?? threadTitle(thread)

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-[#f5f5f5]">
      {/* 대화창 헤더 */}
      <div className="flex h-16 shrink-0 items-center justify-between gap-2 border-b border-slate-200 bg-white px-3 sm:px-5">
        <div className="flex min-w-0 items-center gap-1.5">
          <button
            type="button"
            onClick={onBack}
            className="shrink-0 rounded-md p-1.5 text-slate-500 hover:bg-slate-100 md:hidden"
            aria-label="상담 목록으로"
          >
            <ArrowLeft size={18} />
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="truncate text-base font-bold text-slate-900">
                {threadTitle(thread)}
              </h2>
              {thread.contact_name && thread.client_name && (
                <span className="shrink-0 text-xs text-slate-500">{thread.contact_name}</span>
              )}
            </div>
            <p className="mt-0.5 truncate text-xs text-slate-500">{contextLine}</p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {/* AI↔직원 모드 토글 (세그먼트) */}
          <div
            className="hidden items-center rounded-md border border-slate-200 bg-slate-100 p-1 sm:flex"
            role="group"
            aria-label="응대 모드"
          >
            <button
              type="button"
              onClick={() => switchMode('HUMAN')}
              disabled={closed || update.isPending}
              className={`rounded px-3 py-1.5 text-xs transition-colors disabled:opacity-60 ${
                thread.mode === 'HUMAN'
                  ? 'bg-white font-bold text-slate-800 shadow-sm'
                  : 'font-medium text-slate-500 hover:text-slate-700'
              }`}
            >
              직원 개입
            </button>
            <button
              type="button"
              onClick={() => switchMode('AI')}
              disabled={closed || update.isPending}
              className={`rounded px-3 py-1.5 text-xs transition-colors disabled:opacity-60 ${
                thread.mode === 'AI'
                  ? 'bg-white font-bold text-slate-800 shadow-sm'
                  : 'font-medium text-slate-500 hover:text-slate-700'
              }`}
            >
              AI 응대
            </button>
          </div>

          {thread.client_id && (
            <Link
              to={`/clients/${thread.client_id}`}
              className="rounded border border-slate-200 bg-white p-1.5 text-slate-400 shadow-sm hover:text-slate-700"
              title="고객사 상세 열기"
              aria-label="고객사 상세 열기"
            >
              <AddressBook size={18} />
            </Link>
          )}

          {!closed && (
            <button
              type="button"
              onClick={() => setCloseOpen(true)}
              className="rounded border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-500 shadow-sm hover:bg-slate-50 hover:text-slate-700"
            >
              상담 종료
            </button>
          )}
        </div>
      </div>

      {/* 모바일 모드 토글 */}
      {!closed && (
        <div className="flex shrink-0 items-center justify-center gap-1 border-b border-slate-200 bg-white p-2 sm:hidden">
          <div className="flex items-center rounded-md border border-slate-200 bg-slate-100 p-1">
            <button
              type="button"
              onClick={() => switchMode('HUMAN')}
              disabled={update.isPending}
              className={`rounded px-3 py-1 text-xs ${
                thread.mode === 'HUMAN'
                  ? 'bg-white font-bold text-slate-800 shadow-sm'
                  : 'font-medium text-slate-500'
              }`}
            >
              직원 개입
            </button>
            <button
              type="button"
              onClick={() => switchMode('AI')}
              disabled={update.isPending}
              className={`rounded px-3 py-1 text-xs ${
                thread.mode === 'AI'
                  ? 'bg-white font-bold text-slate-800 shadow-sm'
                  : 'font-medium text-slate-500'
              }`}
            >
              AI 응대
            </button>
          </div>
        </div>
      )}

      {/* 대화 내용 */}
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4 sm:p-6">
        {isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-14 w-2/3" />
            <Skeleton className="ml-auto h-14 w-1/2" />
            <Skeleton className="h-14 w-3/5" />
          </div>
        ) : messages.length === 0 ? (
          <p className="pt-10 text-center text-sm text-slate-400">
            아직 메시지가 없습니다. 고객이 카카오 채널로 문의하면 여기에 표시됩니다.
          </p>
        ) : (
          grouped.map((group) => (
            <div key={group.dateKey} className="space-y-5">
              {/* 날짜 구분선 */}
              <div className="flex justify-center">
                <span className="rounded-full bg-slate-200/60 px-3 py-1 text-[10px] font-medium text-slate-500">
                  {group.heading}
                </span>
              </div>
              {group.items.map((m) => (
                <MessageBubble
                  key={m.message_id}
                  message={m}
                  customerName={customerName}
                  undelivered={isUndelivered(m)}
                />
              ))}
            </div>
          ))
        )}
      </div>

      {/* 입력 영역 */}
      <div className="shrink-0 border-t border-slate-200 bg-white p-3 sm:p-4">
        {closed ? (
          <p className="py-2 text-center text-xs text-slate-400">
            종료된 상담입니다. 고객이 다시 문의하면 새 대화가 이어집니다.
          </p>
        ) : (
          <>
            <div className="flex items-end gap-2 sm:gap-3">
              <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-slate-200 bg-slate-50 transition-colors focus-within:border-slate-400 focus-within:bg-white">
                <textarea
                  ref={taRef}
                  rows={2}
                  value={text}
                  maxLength={MAX_LEN}
                  onChange={(e) => {
                    setText(e.target.value)
                    autoResize()
                  }}
                  onKeyDown={onKeyDown}
                  placeholder="고객에게 전송할 메시지를 입력하세요. (Enter 전송 · Shift+Enter 줄바꿈)"
                  className="w-full resize-none bg-transparent p-3 text-sm text-slate-800 outline-none"
                  aria-label="메시지 입력"
                />
              </div>
              <button
                type="button"
                onClick={send}
                disabled={!text.trim() || reply.isPending}
                className="flex shrink-0 flex-col items-center justify-center rounded-lg bg-slate-800 px-3.5 py-3 text-white shadow-sm transition-colors hover:bg-slate-700 disabled:opacity-50"
                aria-label="전송"
              >
                {reply.isPending ? (
                  <CircleNotch size={20} className="animate-spin" />
                ) : (
                  <PaperPlaneRight size={20} weight="fill" />
                )}
                <span className="mt-0.5 text-[10px] font-medium">전송</span>
              </button>
            </div>
            <div className="mt-2 flex items-center justify-between px-1 text-[10px] text-slate-400">
              <span className="truncate">
                {thread.mode === 'HUMAN'
                  ? '직원 개입 모드 — 메시지를 보내면 고객의 카카오톡으로 즉시 전송됩니다.'
                  : 'AI 자동 응대 모드 — 메시지를 보내면 직원 개입 모드로 자동 전환됩니다.'}
              </span>
              <span className={`shrink-0 ${text.length >= MAX_LEN ? 'font-bold text-rose-500' : ''}`}>
                {text.length} / {MAX_LEN}자
              </span>
            </div>
          </>
        )}
      </div>

      {/* 상담 종료 확인 */}
      <ConfirmDialog
        open={closeOpen}
        title="상담 종료"
        message={
          <>
            <b>{threadTitle(thread)}</b> 상담을 종료합니다.
            <br />
            종료 시 상담 내용 요약이 활동 이력(카카오·자동)으로 기록됩니다. 고객이 다시
            문의하면 대화가 새로 이어집니다.
          </>
        }
        confirmLabel="종료"
        danger
        loading={update.isPending}
        onConfirm={closeThread}
        onCancel={() => setCloseOpen(false)}
      />
    </div>
  )
}

// ── 말풍선 4종: CUSTOMER(좌·흰) / AI(좌·회색+로봇) / STAFF(우·다크) / SYSTEM(중앙 rose) ──
function MessageBubble({
  message,
  customerName,
  undelivered,
}: {
  message: ChatMessage
  customerName: string
  undelivered: boolean
}) {
  const time = fmtKakaoTime(message.created_at)

  if (message.sender_type === 'SYSTEM') {
    return (
      <div className="my-4 flex justify-center">
        <div className="max-w-md rounded-md border border-rose-100 bg-rose-50 px-4 py-2 text-center">
          <div className="flex items-center justify-center gap-1 text-xs font-bold text-rose-700">
            <WarningCircle size={13} weight="fill" />
            시스템 알림
          </div>
          <div className="mt-0.5 text-[10px] whitespace-pre-wrap text-slate-600">
            {message.content}
          </div>
        </div>
      </div>
    )
  }

  if (message.sender_type === 'STAFF') {
    return (
      <div className="flex flex-col items-end gap-1">
        <div className="mr-1 flex items-center gap-2">
          {undelivered && (
            <span className="flex items-center gap-0.5 text-[10px] font-bold text-rose-600">
              <WarningCircle size={11} weight="fill" />
              미전달
            </span>
          )}
          <span className="text-[10px] text-slate-400">{time}</span>
          <span className="text-xs font-bold text-slate-700">
            {message.sender_name ?? '직원'}
          </span>
        </div>
        <div
          className={`max-w-md rounded-lg rounded-tr-none bg-slate-800 p-3 text-sm whitespace-pre-wrap text-white shadow-sm ${
            undelivered ? 'opacity-80 ring-1 ring-rose-300' : ''
          }`}
        >
          {message.content}
        </div>
      </div>
    )
  }

  const isAi = message.sender_type === 'AI'
  return (
    <div className="flex flex-col items-start gap-1">
      <div className="ml-1 flex items-center gap-2">
        {isAi && (
          <span className="rounded bg-slate-200 p-1">
            <Robot size={12} weight="fill" className="text-slate-600" />
          </span>
        )}
        <span className="text-xs font-bold text-slate-700">
          {isAi ? 'AI 어시스턴트' : (message.sender_name ?? customerName)}
        </span>
        <span className="text-[10px] text-slate-400">{time}</span>
      </div>
      <div
        className={`max-w-md rounded-lg rounded-tl-none border border-slate-200 p-3 text-sm whitespace-pre-wrap ${
          isAi ? 'bg-slate-100 text-slate-700' : 'bg-white text-slate-800 shadow-sm'
        }`}
      >
        {message.content}
      </div>
    </div>
  )
}
