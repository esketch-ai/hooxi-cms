// SCR-08 스레드 상태·모드 pill — 리스트·고객사 상세 상담 탭 공용 (목업 08_chat.html)
import { CheckCircle, Robot, User } from '@phosphor-icons/react'
import type { ChatThread } from '../../types'

/** 응대 모드 pill: AI 로봇 / 직원 상담 / 상담 종료 */
export function ThreadModePill({ thread }: { thread: ChatThread }) {
  if (thread.status === 'CLOSED') {
    return (
      <span className="inline-flex items-center gap-1 rounded-sm border border-hairline bg-elevate-strong px-1.5 py-0.5 text-[10px] font-medium text-ash">
        <CheckCircle size={11} weight="fill" className="text-slatey" />
        상담 종료
      </span>
    )
  }
  if (thread.mode === 'HUMAN') {
    return (
      <span className="inline-flex items-center gap-1 rounded-sm border border-hairline bg-elevate-strong px-1.5 py-0.5 text-[10px] font-medium text-ash">
        <User size={11} weight="fill" className="text-slatey" />
        직원 상담 중
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-sm border border-hairline bg-elevate-strong px-1.5 py-0.5 text-[10px] font-medium text-ash">
      <Robot size={11} weight="fill" className="text-slatey" />
      AI 자동 응대
    </span>
  )
}

/** 직원 연결 대기(WAITING) rose 뱃지 */
export function ThreadWaitingBadge({ thread }: { thread: ChatThread }) {
  if (thread.status !== 'WAITING') return null
  return (
    <span className="inline-flex items-center rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] font-bold text-rose-700 dark:text-rose-300">
      연결 대기
    </span>
  )
}
