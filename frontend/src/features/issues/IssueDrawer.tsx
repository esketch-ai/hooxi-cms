// SCR-02 이슈 카드 상세 Drawer — 내용·코멘트 스레드·상태 변경 이력·고객사 딥링크
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowSquareOut, CircleNotch, PaperPlaneRight, Phone } from '@phosphor-icons/react'
import { Drawer } from '../../components/Drawer'
import { StatusBadge } from '../../components/StatusBadge'
import { AuditLine } from '../../components/AuditLine'
import { Skeleton } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { dday, elapsedServer, fmtServerDateTime, telHref } from '../../lib/format'
import { useCodes, useUserOptions } from '../../lib/api/queries'
import type { ActivityHistory, IssueStatus } from '../../types'
import { useClient } from '../clients/api'
import {
  useAddIssueComment,
  useChangeIssueManager,
  useChangeIssueStatus,
  useIssueComments,
} from './api'

interface IssueDrawerProps {
  issue: ActivityHistory | null
  onClose: () => void
}

// 이슈 본문의 URL을 클릭 가능한 링크로 렌더 — 반자동 계정 점검의 '로그인 바로가기' 딥링크 등.
// split(캡처 그룹)은 [텍스트, URL, 텍스트, ...]로 분리되어 홀수 인덱스가 URL (stateful test 회피).
function renderWithLinks(text: string): ReactNode[] {
  return text.split(/(https?:\/\/[^\s]+)/g).map((part, i) =>
    i % 2 === 1 ? (
      <a
        key={i}
        href={part}
        target="_blank"
        rel="noopener noreferrer"
        className="break-all text-primary underline hover:opacity-80"
      >
        {part}
      </a>
    ) : (
      part
    ),
  )
}

export function IssueDrawer({ issue, onClose }: IssueDrawerProps) {
  const { showToast } = useToast()
  const { options: statusOptions } = useCodes('ISSUE_STATUS')
  const { data: comments = [], isLoading: commentsLoading } = useIssueComments(
    issue?.history_id,
  )
  const changeStatus = useChangeIssueStatus()
  const changeManager = useChangeIssueManager()
  const addComment = useAddIssueComment(issue?.history_id)
  const { data: users = [] } = useUserOptions()
  // 고객사 전화번호는 이슈 상세에 포함되지 않으므로 client_id로 고객사 상세를 조회한다.
  const { data: client } = useClient(issue?.client_id ?? undefined)
  const [newComment, setNewComment] = useState('')

  if (!issue) return null

  const due = dday(issue.due_date)
  const clientPhone = client?.main_contact_phone

  const handleStatusChange = async (next: IssueStatus) => {
    if (next === issue.issue_status) return
    try {
      await changeStatus.mutateAsync({ historyId: issue.history_id, issueStatus: next })
      showToast('이슈 상태가 변경되었습니다.', 'success')
    } catch {
      showToast('상태 변경에 실패했습니다.', 'danger')
    }
  }

  // 담당자 인계 (P1-D) — 409(동시 인계)·422(비활성 사용자) 서버 detail 그대로 노출
  const handleManagerChange = async (managerId: string) => {
    if (!managerId || managerId === issue.manager_id) return
    try {
      await changeManager.mutateAsync({ historyId: issue.history_id, managerId })
      showToast('담당자가 변경되었습니다.', 'success')
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      showToast(detail ?? '담당자 변경에 실패했습니다.', 'danger')
    }
  }

  const handleAddComment = async (e: FormEvent) => {
    e.preventDefault()
    if (!newComment.trim()) return
    try {
      await addComment.mutateAsync(newComment.trim())
      setNewComment('')
    } catch {
      showToast('코멘트 등록에 실패했습니다.', 'danger')
    }
  }

  return (
    <Drawer
      open={!!issue}
      onClose={onClose}
      size="lg"
      title={
        <div className="flex items-center gap-2">
          {issue.priority === 'URGENT' && (
            <span className="rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] font-bold text-rose-700 dark:text-rose-300">
              긴급
            </span>
          )}
          <span className="truncate">{issue.title}</span>
        </div>
      }
    >
      <div className="space-y-5">
        {/* 메타 */}
        <div className="flex flex-wrap items-center gap-2">
          {issue.issue_status && <StatusBadge domain="issue" value={issue.issue_status} />}
          {due && (
            <span
              className={`text-xs font-semibold ${
                due.overdue || due.imminent ? 'text-rose-700 dark:text-rose-300' : 'text-ash'
              }`}
            >
              마감 {due.label}
            </span>
          )}
          <span className="text-xs text-slatey">
            접수 {fmtServerDateTime(issue.created_at)} · {elapsedServer(issue.created_at)}
          </span>
        </div>

        {/* 고객사 딥링크 + 담당자 전화 (Click-to-Call) */}
        {issue.client_id && (
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to={`/clients/${issue.client_id}`}
              className="flex items-center gap-1.5 rounded-lg border border-hairline bg-elevate px-3 py-2 text-sm font-semibold text-bone hover:bg-elevate-strong"
            >
              {issue.client_name ?? '고객사'}
              <ArrowSquareOut size={14} className="text-slatey" />
            </Link>
            {clientPhone && (
              <a
                href={telHref(clientPhone)}
                className="flex items-center gap-1.5 rounded-lg border border-emerald-400/25 bg-emerald-500/15 px-3 py-2 text-sm font-semibold text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/25"
              >
                <Phone size={15} weight="fill" />
                {clientPhone}
              </a>
            )}
          </div>
        )}

        {/* 상태 변경 */}
        <div>
          <p className="mb-1.5 text-xs font-semibold text-slatey">상태 변경</p>
          <div className="flex gap-1.5">
            {statusOptions.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => handleStatusChange(opt.value as IssueStatus)}
                disabled={changeStatus.isPending}
                className={`flex-1 rounded-lg border px-2 py-1.5 text-xs font-medium disabled:opacity-60 ${
                  issue.issue_status === opt.value
                    ? 'border-snow bg-primary text-on-primary'
                    : 'border-hairline text-bone hover:bg-elevate'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* 담당자 인계 — 변경 시 ASSIGN 코멘트 자동 적재 (P1-D) */}
        <div>
          <p className="mb-1.5 text-xs font-semibold text-slatey">담당자</p>
          {users.length === 0 ? (
            /* 사용자 목록 권한 없음(403 폴백) — 현재 담당자만 표시 */
            <p className="text-sm text-bone">{issue.manager_name ?? '—'}</p>
          ) : (
            <select
              value={issue.manager_id}
              onChange={(e) => void handleManagerChange(e.target.value)}
              disabled={changeManager.isPending}
              className="h-9 w-full rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none disabled:opacity-60"
              aria-label="담당자 변경"
            >
              {/* 현 담당자가 비활성 등으로 목록에 없어도 현재 값은 표시 */}
              {!users.some((u) => u.user_id === issue.manager_id) && (
                <option value={issue.manager_id}>{issue.manager_name ?? issue.manager_id}</option>
              )}
              {users.map((u) => (
                <option key={u.user_id} value={u.user_id}>
                  {u.name}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* 내용 */}
        <div>
          <p className="mb-1 text-xs font-semibold text-slatey">이슈 내용</p>
          <p className="text-sm leading-relaxed whitespace-pre-wrap text-bone">
            {issue.content ? renderWithLinks(issue.content) : '—'}
          </p>
          {issue.main_needs && (
            <p className="mt-2 text-sm text-ash">주요 니즈: {issue.main_needs}</p>
          )}
          <AuditLine
            createdByName={issue.created_by_name ?? issue.manager_name}
            createdAt={issue.created_at}
            className="mt-2"
          />
        </div>

        {/* 코멘트 스레드 + 상태 변경 이력 (부서원 누구나 기록) */}
        <div>
          <p className="mb-2 text-xs font-semibold text-slatey">
            처리 코멘트 · 변경 이력
          </p>
          {commentsLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-4/5" />
            </div>
          ) : comments.length === 0 ? (
            <p className="rounded-lg border border-dashed border-hairline py-4 text-center text-xs text-slatey">
              아직 코멘트가 없습니다
            </p>
          ) : (
            <ul className="space-y-2.5">
              {comments.map((c) => (
                <li key={c.comment_id}>
                  {c.comment_type === 'COMMENT' ? (
                    <div className="rounded-lg bg-elevate px-3 py-2">
                      <p className="text-sm whitespace-pre-wrap text-bone">{c.content}</p>
                      <p className="mt-1 text-[11px] text-slatey">
                        {c.manager_name ?? '—'} · {fmtServerDateTime(c.created_at)}
                      </p>
                    </div>
                  ) : (
                    /* 상태·담당 변경 자동 적재 (GAN A4) */
                    <p className="px-1 text-[11px] text-slatey">
                      <span className="mr-1 inline-flex rounded bg-elevate-strong px-1 py-0.5 text-[10px] font-medium text-ash">
                        {c.comment_type === 'STATUS_CHANGE' ? '상태 변경' : '담당 변경'}
                      </span>
                      {c.content} — {c.manager_name ?? '—'} · {fmtServerDateTime(c.created_at)}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}

          {/* 코멘트 입력 */}
          <form onSubmit={handleAddComment} className="mt-3 flex gap-2">
            <input
              value={newComment}
              onChange={(e) => setNewComment(e.target.value)}
              placeholder="처리 코멘트 입력"
              className="h-10 flex-1 rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
            />
            <button
              type="submit"
              disabled={addComment.isPending || !newComment.trim()}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary text-on-primary hover:opacity-90 disabled:opacity-50"
              aria-label="코멘트 등록"
            >
              {addComment.isPending ? (
                <CircleNotch size={16} className="animate-spin" />
              ) : (
                <PaperPlaneRight size={16} weight="fill" />
              )}
            </button>
          </form>
        </div>
      </div>
    </Drawer>
  )
}
