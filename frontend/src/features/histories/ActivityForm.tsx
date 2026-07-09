// 공용 활동 이력 등록 폼 (SCR-05) — 고객사 상세·이슈 보드·대시보드에서 재사용
import { useEffect, useState, type FormEvent } from 'react'
import { CircleNotch } from '@phosphor-icons/react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Modal } from '../../components/Modal'
import { useToast } from '../../components/Toast'
import { api } from '../../lib/api/client'
import { useClientOptions } from '../../lib/api/queries'
import { toDatetimeLocal } from '../../lib/format'
import type { ActivityPayload, ActivityType, IssueStatus } from '../../types'

const inputCls =
  'h-10 w-full rounded-lg border border-slate-200 px-3 text-sm focus:border-slate-500 focus:outline-none'
const labelCls = 'mb-1 block text-xs font-medium text-slate-600'

const ACTIVITY_TYPES: { value: ActivityType; label: string }[] = [
  { value: 'CALL', label: '전화' },
  { value: 'MEETING', label: '미팅' },
  { value: 'SITE_VISIT', label: '현장방문' },
  { value: 'EMAIL', label: '이메일' },
  { value: 'ISSUE', label: '이슈' },
  { value: 'KAKAO', label: '카카오' },
]

const RETENTION_STAGES = [
  { value: 'AWARENESS', label: '인지' },
  { value: 'INTEREST', label: '관심' },
  { value: 'REVIEW', label: '검토' },
  { value: 'DECISION', label: '구매결정' },
  { value: 'ONBOARDING', label: '온보딩' },
  { value: 'UTILIZATION', label: '활용' },
  { value: 'RENEWAL', label: '재계약' },
  { value: 'EXPANSION', label: '확장' },
]

interface ActivityFormProps {
  open: boolean
  onClose: () => void
  /** 고객사 상세 등에서 고객사 고정 */
  defaultClientId?: string | null
  lockClient?: boolean
  /** 이슈 보드에서 유형=ISSUE 기본 */
  defaultType?: ActivityType
  onCreated?: () => void
}

export function ActivityForm({
  open,
  onClose,
  defaultClientId,
  lockClient = false,
  defaultType = 'CALL',
  onCreated,
}: ActivityFormProps) {
  const { showToast } = useToast()
  const { data: clients = [] } = useClientOptions()
  const queryClient = useQueryClient()

  const [clientId, setClientId] = useState(defaultClientId ?? '')
  const [activityDate, setActivityDate] = useState(() => toDatetimeLocal(new Date()))
  const [activityType, setActivityType] = useState<ActivityType>(defaultType)
  const [retentionStage, setRetentionStage] = useState('')
  const [issueStatus, setIssueStatus] = useState<IssueStatus>('OPEN')
  const [priority, setPriority] = useState<'URGENT' | 'NORMAL'>('NORMAL')
  const [dueDate, setDueDate] = useState('')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [mainNeeds, setMainNeeds] = useState('')
  const [nextAction, setNextAction] = useState('')

  useEffect(() => {
    if (open) {
      setClientId(defaultClientId ?? '')
      setActivityDate(toDatetimeLocal(new Date()))
      setActivityType(defaultType)
      setRetentionStage('')
      setIssueStatus('OPEN')
      setPriority('NORMAL')
      setDueDate('')
      setTitle('')
      setContent('')
      setMainNeeds('')
      setNextAction('')
    }
  }, [open, defaultClientId, defaultType])

  const create = useMutation({
    mutationFn: async (payload: ActivityPayload) => {
      const { data } = await api.post('/histories', payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['histories'] })
      queryClient.invalidateQueries({ queryKey: ['issues'] })
      queryClient.invalidateQueries({ queryKey: ['clients'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  const isIssue = activityType === 'ISSUE'

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!clientId) {
      showToast('고객사를 선택해 주세요.', 'danger')
      return
    }
    if (!title.trim() || !content.trim()) {
      showToast('제목과 상세 내용을 입력해 주세요.', 'danger')
      return
    }
    try {
      await create.mutateAsync({
        client_id: clientId,
        activity_date: activityDate,
        activity_type: activityType,
        retention_stage: retentionStage || null,
        issue_status: isIssue ? issueStatus : null,
        priority: isIssue ? priority : null,
        due_date: isIssue && dueDate ? dueDate : null,
        next_action: nextAction || null,
        title: title.trim(),
        content: content.trim(),
        main_needs: mainNeeds || null,
      })
      showToast('활동 이력이 등록되었습니다.', 'success')
      onCreated?.()
      onClose()
    } catch {
      showToast('등록에 실패했습니다. 잠시 후 다시 시도해 주세요.', 'danger')
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="활동 이력 등록" size="lg">
      <form onSubmit={handleSubmit} className="max-h-[70vh] space-y-3 overflow-y-auto pr-1">
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className={labelCls}>
              고객사<span className="ml-0.5 text-rose-500">*</span>
            </label>
            <select
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              disabled={lockClient}
              className={`${inputCls} disabled:bg-slate-50 disabled:text-slate-500`}
            >
              <option value="">선택</option>
              {clients.map((c) => (
                <option key={c.client_id} value={c.client_id}>
                  {c.company_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelCls}>
              일시<span className="ml-0.5 text-rose-500">*</span>
            </label>
            <input
              type="datetime-local"
              value={activityDate}
              onChange={(e) => setActivityDate(e.target.value)}
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>
              유형<span className="ml-0.5 text-rose-500">*</span>
            </label>
            <select
              value={activityType}
              onChange={(e) => setActivityType(e.target.value as ActivityType)}
              className={inputCls}
            >
              {ACTIVITY_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelCls}>리텐션 단계</label>
            <select
              value={retentionStage}
              onChange={(e) => setRetentionStage(e.target.value)}
              className={inputCls}
            >
              <option value="">선택 안 함</option>
              {RETENTION_STAGES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* 유형=ISSUE일 때만 노출 */}
        {isIssue && (
          <div className="grid gap-3 rounded-lg border border-rose-100 bg-rose-50/50 p-3 sm:grid-cols-3">
            <div>
              <label className={labelCls}>이슈 상태</label>
              <select
                value={issueStatus}
                onChange={(e) => setIssueStatus(e.target.value as IssueStatus)}
                className={inputCls}
              >
                <option value="OPEN">접수</option>
                <option value="IN_PROGRESS">처리중</option>
                <option value="HOLD">보류</option>
                <option value="CLOSED">완료</option>
              </select>
            </div>
            <div>
              <label className={labelCls}>긴급도</label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as 'URGENT' | 'NORMAL')}
                className={inputCls}
              >
                <option value="NORMAL">일반</option>
                <option value="URGENT">긴급</option>
              </select>
            </div>
            <div>
              <label className={labelCls}>마감일</label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className={inputCls}
              />
            </div>
          </div>
        )}

        <div>
          <label className={labelCls}>
            제목<span className="ml-0.5 text-rose-500">*</span>
          </label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={inputCls}
            placeholder="요약 한 줄"
          />
        </div>
        <div>
          <label className={labelCls}>
            상세 내용<span className="ml-0.5 text-rose-500">*</span>
          </label>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={4}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className={labelCls}>주요 니즈</label>
            <input
              value={mainNeeds}
              onChange={(e) => setMainNeeds(e.target.value)}
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>Next Action</label>
            <input
              value={nextAction}
              onChange={(e) => setNextAction(e.target.value)}
              className={inputCls}
              placeholder="다음 조치 사항"
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-100 pt-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={create.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-60"
          >
            {create.isPending && <CircleNotch size={14} className="animate-spin" />}
            등록
          </button>
        </div>
      </form>
    </Modal>
  )
}
