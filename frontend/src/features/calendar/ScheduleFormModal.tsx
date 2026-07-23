// SCR-11 일정 등록 Modal
import { useEffect, useState, type FormEvent } from 'react'
import { CircleNotch } from '@phosphor-icons/react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Modal } from '../../components/Modal'
import { useToast } from '../../components/Toast'
import { api } from '../../lib/api/client'
import { useClientOptions } from '../../lib/api/queries'
import { toDatetimeLocal } from '../../lib/format'
import type { Schedule, SchedulePayload, ScheduleType } from '../../types'

const inputCls =
  'h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none'
const labelCls = 'mb-1 block text-xs font-medium text-ash'

const TYPE_OPTIONS: { value: ScheduleType; label: string }[] = [
  { value: 'MEETING', label: '미팅' },
  { value: 'CALL', label: '전화' },
  { value: 'SITE_VISIT', label: '현장방문' },
  { value: 'INTERNAL', label: '내부 일정' },
]

interface ScheduleFormModalProps {
  open: boolean
  onClose: () => void
  /** 캘린더 빈 칸 클릭 시 해당 일자 기본값 */
  defaultDate?: Date | null
  /** 지정 시 수정 모드 — 해당 일정을 프리필하고 PUT으로 저장 */
  editing?: Schedule | null
}

export function ScheduleFormModal({ open, onClose, defaultDate, editing }: ScheduleFormModalProps) {
  const { showToast } = useToast()
  const { data: clients = [] } = useClientOptions()
  const queryClient = useQueryClient()

  const [scheduleType, setScheduleType] = useState<ScheduleType>('MEETING')
  const [title, setTitle] = useState('')
  const [clientId, setClientId] = useState('')
  const [startAt, setStartAt] = useState('')
  const [endAt, setEndAt] = useState('')
  const [location, setLocation] = useState('')
  const [memo, setMemo] = useState('')
  const [monthly, setMonthly] = useState(false)

  useEffect(() => {
    if (!open) return
    if (editing) {
      // 수정 모드 — 기존 값 프리필 (REPORT_DUE 등 폼에 없는 유형은 MEETING로 폴백)
      const t = editing.schedule_type as ScheduleType
      setScheduleType(TYPE_OPTIONS.some((o) => o.value === t) ? t : 'MEETING')
      setTitle(editing.title ?? '')
      setClientId(editing.client_id ?? '')
      setStartAt(editing.start_at ? toDatetimeLocal(new Date(editing.start_at)) : '')
      setEndAt(editing.end_at ? toDatetimeLocal(new Date(editing.end_at)) : '')
      setLocation(editing.location ?? '')
      setMemo(editing.memo ?? '')
      setMonthly(false)
      return
    }
    const base = defaultDate ?? new Date()
    base.setHours(10, 0, 0, 0)
    setScheduleType('MEETING')
    setTitle('')
    setClientId('')
    setStartAt(toDatetimeLocal(base))
    setEndAt('')
    setLocation('')
    setMemo('')
    setMonthly(false)
  }, [open, defaultDate, editing])

  const create = useMutation({
    mutationFn: async (payload: SchedulePayload) => {
      if (editing) {
        const { data } = await api.put(`/schedules/${editing.schedule_id}`, payload)
        return data
      }
      const { data } = await api.post('/schedules', payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] })
    },
  })

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!title.trim()) {
      showToast('일정 제목을 입력해 주세요.', 'danger')
      return
    }
    if (!startAt) {
      showToast('시작 일시를 입력해 주세요.', 'danger')
      return
    }
    try {
      await create.mutateAsync({
        schedule_type: scheduleType,
        title: title.trim(),
        client_id: clientId || null,
        start_at: startAt,
        end_at: endAt || null,
        location: location || null,
        memo: memo || null,
        recur_rule: monthly ? 'MONTHLY' : null,
      })
      showToast(editing ? '일정이 수정되었습니다.' : '일정이 등록되었습니다.', 'success')
      onClose()
    } catch {
      showToast(editing ? '일정 수정에 실패했습니다.' : '일정 등록에 실패했습니다.', 'danger')
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={editing ? '일정 수정' : '일정 등록'} size="md">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className={labelCls}>
              유형<span className="ml-0.5 text-rose-500">*</span>
            </label>
            <select
              value={scheduleType}
              onChange={(e) => setScheduleType(e.target.value as ScheduleType)}
              className={inputCls}
            >
              {TYPE_OPTIONS.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelCls}>고객사 (내부 일정은 비움)</label>
            <select
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              className={inputCls}
            >
              <option value="">선택 안 함</option>
              {clients.map((c) => (
                <option key={c.client_id} value={c.client_id}>
                  {c.company_name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label className={labelCls}>
            제목<span className="ml-0.5 text-rose-500">*</span>
          </label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={inputCls}
            placeholder="예: 대성운수 정기 미팅"
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className={labelCls}>
              시작<span className="ml-0.5 text-rose-500">*</span>
            </label>
            <input
              type="datetime-local"
              value={startAt}
              onChange={(e) => setStartAt(e.target.value)}
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>종료</label>
            <input
              type="datetime-local"
              value={endAt}
              onChange={(e) => setEndAt(e.target.value)}
              className={inputCls}
            />
          </div>
        </div>
        <div>
          <label className={labelCls}>장소 (현장 주소 — 내비 딥링크 원천)</label>
          <input value={location} onChange={(e) => setLocation(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>메모</label>
          <textarea
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
            rows={3}
            className="w-full rounded-lg border border-hairline bg-graphite px-3 py-2 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
          />
        </div>
        {!editing && (
          <label className="flex items-center gap-2 text-sm text-ash">
            <input
              type="checkbox"
              checked={monthly}
              onChange={(e) => setMonthly(e.target.checked)}
              className="h-4 w-4 rounded border-hairline-strong"
            />
            매월 반복
          </label>
        )}

        <div className="flex justify-end gap-2 border-t border-hairline pt-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={create.isPending}
            className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-60"
          >
            {create.isPending && <CircleNotch size={14} className="animate-spin" />}
            {editing ? '저장' : '등록'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
