// SCR-02 이슈 카드 상세 Drawer — 내용·코멘트 스레드·상태 변경 이력·고객사 딥링크
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ArrowSquareOut, CircleNotch, PaperPlaneRight } from '@phosphor-icons/react'
import { Drawer } from '../../components/Drawer'
import { StatusBadge } from '../../components/StatusBadge'
import { AuditLine } from '../../components/AuditLine'
import { Skeleton } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { dday, elapsedServer, fmtServerDateTime } from '../../lib/format'
import type { ActivityHistory, IssueStatus } from '../../types'
import { useAddIssueComment, useChangeIssueStatus, useIssueComments } from './api'

const STATUS_OPTIONS: { value: IssueStatus; label: string }[] = [
  { value: 'OPEN', label: '접수' },
  { value: 'IN_PROGRESS', label: '처리중' },
  { value: 'HOLD', label: '보류' },
  { value: 'CLOSED', label: '완료' },
]

interface IssueDrawerProps {
  issue: ActivityHistory | null
  onClose: () => void
}

export function IssueDrawer({ issue, onClose }: IssueDrawerProps) {
  const { showToast } = useToast()
  const { data: comments = [], isLoading: commentsLoading } = useIssueComments(
    issue?.history_id,
  )
  const changeStatus = useChangeIssueStatus()
  const addComment = useAddIssueComment(issue?.history_id)
  const [newComment, setNewComment] = useState('')

  if (!issue) return null

  const due = dday(issue.due_date)

  const handleStatusChange = async (next: IssueStatus) => {
    if (next === issue.issue_status) return
    try {
      await changeStatus.mutateAsync({ historyId: issue.history_id, issueStatus: next })
      showToast('이슈 상태가 변경되었습니다.', 'success')
    } catch {
      showToast('상태 변경에 실패했습니다.', 'danger')
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
            <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-bold text-rose-600">
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
                due.overdue || due.imminent ? 'text-rose-600' : 'text-slate-500'
              }`}
            >
              마감 {due.label}
            </span>
          )}
          <span className="text-xs text-slate-400">
            접수 {fmtServerDateTime(issue.created_at)} · {elapsedServer(issue.created_at)}
          </span>
        </div>

        {/* 고객사 딥링크 */}
        {issue.client_id && (
          <Link
            to={`/clients/${issue.client_id}`}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100"
          >
            {issue.client_name ?? '고객사'}
            <ArrowSquareOut size={14} className="text-slate-400" />
          </Link>
        )}

        {/* 상태 변경 */}
        <div>
          <p className="mb-1.5 text-xs font-semibold text-slate-400">상태 변경</p>
          <div className="flex gap-1.5">
            {STATUS_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => handleStatusChange(opt.value)}
                disabled={changeStatus.isPending}
                className={`flex-1 rounded-lg border px-2 py-1.5 text-xs font-medium disabled:opacity-60 ${
                  issue.issue_status === opt.value
                    ? 'border-slate-800 bg-slate-800 text-white'
                    : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* 내용 */}
        <div>
          <p className="mb-1 text-xs font-semibold text-slate-400">이슈 내용</p>
          <p className="text-sm leading-relaxed whitespace-pre-wrap text-slate-700">
            {issue.content || '—'}
          </p>
          {issue.main_needs && (
            <p className="mt-2 text-sm text-slate-500">주요 니즈: {issue.main_needs}</p>
          )}
          <AuditLine
            createdByName={issue.created_by_name ?? issue.manager_name}
            createdAt={issue.created_at}
            className="mt-2"
          />
        </div>

        {/* 코멘트 스레드 + 상태 변경 이력 (부서원 누구나 기록) */}
        <div>
          <p className="mb-2 text-xs font-semibold text-slate-400">
            처리 코멘트 · 변경 이력
          </p>
          {commentsLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-4/5" />
            </div>
          ) : comments.length === 0 ? (
            <p className="rounded-lg border border-dashed border-slate-200 py-4 text-center text-xs text-slate-400">
              아직 코멘트가 없습니다
            </p>
          ) : (
            <ul className="space-y-2.5">
              {comments.map((c) => (
                <li key={c.comment_id}>
                  {c.comment_type === 'COMMENT' ? (
                    <div className="rounded-lg bg-slate-50 px-3 py-2">
                      <p className="text-sm whitespace-pre-wrap text-slate-700">{c.content}</p>
                      <p className="mt-1 text-[11px] text-slate-400">
                        {c.manager_name ?? '—'} · {fmtServerDateTime(c.created_at)}
                      </p>
                    </div>
                  ) : (
                    /* 상태·담당 변경 자동 적재 (GAN A4) */
                    <p className="px-1 text-[11px] text-slate-400">
                      <span className="mr-1 inline-flex rounded bg-slate-100 px-1 py-0.5 text-[10px] font-medium">
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
              className="h-10 flex-1 rounded-lg border border-slate-200 px-3 text-sm focus:border-slate-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={addComment.isPending || !newComment.trim()}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50"
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
