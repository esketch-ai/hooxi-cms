// 공용 활동 이력 등록 폼 (SCR-05) — 고객사 상세·이슈 보드·대시보드에서 재사용
import { useEffect, useState, type FormEvent } from 'react'
import { CircleNotch, FileImage, X } from '@phosphor-icons/react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { FileUploader } from '../../components/FileUploader'
import { Modal } from '../../components/Modal'
import { useToast } from '../../components/Toast'
import { api } from '../../lib/api/client'
import { useClientOptions, useCodes } from '../../lib/api/queries'
import { toDatetimeLocal } from '../../lib/format'
import type { ActivityHistory, ActivityPayload, ActivityType, IssueStatus } from '../../types'

const inputCls =
  'h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none'
const labelCls = 'mb-1 block text-xs font-medium text-ash'

/** 고객사 select에서 '신규 업체 직접 입력'을 나타내는 특수 값 */
const NEW_CLIENT = '__new__'

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
  const { options: clientTypeOptions } = useCodes('CLIENT_TYPE')
  const { options: activityTypeOptions } = useCodes('ACTIVITY_TYPE')
  const queryClient = useQueryClient()

  const [clientId, setClientId] = useState(defaultClientId ?? '')
  // 신규 업체 인라인 등록 (clientId === NEW_CLIENT일 때)
  const [newCompanyName, setNewCompanyName] = useState('')
  const [newClientType, setNewClientType] = useState('TRANSPORT')
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
  // 현장 사진 첨부 — 이력 저장 후 history_id로 순차 업로드 (태블릿 촬영 지원)
  const [photos, setPhotos] = useState<File[]>([])

  useEffect(() => {
    if (open) {
      setClientId(defaultClientId ?? '')
      setNewCompanyName('')
      setNewClientType(clientTypeOptions[0]?.value ?? 'TRANSPORT')
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
      setPhotos([])
    }
  }, [open, defaultClientId, defaultType])

  const create = useMutation({
    mutationFn: async (payload: ActivityPayload) => {
      const { data } = await api.post<ActivityHistory>('/histories', payload)
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
    if (clientId === NEW_CLIENT && !newCompanyName.trim()) {
      showToast('신규 업체명을 입력해 주세요.', 'danger')
      return
    }
    if (!title.trim() || !content.trim()) {
      showToast('제목과 상세 내용을 입력해 주세요.', 'danger')
      return
    }
    try {
      let resolvedClientId = clientId
      if (clientId === NEW_CLIENT) {
        // 업체명·구분만으로 간편 등록 — 상세 정보는 고객사 마스터에서 보완
        const { data: created } = await api.post('/clients', {
          company_name: newCompanyName.trim(),
          client_type: newClientType,
        })
        resolvedClientId = created.client_id
        queryClient.invalidateQueries({ queryKey: ['clients'] })
      }
      const created = await create.mutateAsync({
        client_id: resolvedClientId,
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
      // 이력 저장 완료 후 history_id로 현장 사진 순차 업로드 (실패해도 이력은 유지)
      let photoFailed = 0
      for (const photo of photos) {
        const form = new FormData()
        form.append('file', photo)
        form.append('title', photo.name)
        form.append('doc_type', 'PHOTO')
        form.append('client_id', resolvedClientId)
        form.append('history_id', created.history_id)
        try {
          await api.post('/documents', form, {
            headers: { 'Content-Type': 'multipart/form-data' },
            timeout: 60_000,
          })
        } catch {
          photoFailed += 1
        }
      }
      if (photos.length > 0) {
        queryClient.invalidateQueries({ queryKey: ['documents'] })
      }
      if (photoFailed > 0) {
        showToast(
          `활동 이력은 등록되었으나 사진 ${photoFailed}건 업로드에 실패했습니다.`,
          'danger',
        )
      } else {
        showToast('활동 이력이 등록되었습니다.', 'success')
      }
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
              className={`${inputCls} disabled:bg-elevate disabled:text-slatey`}
            >
              <option value="">선택</option>
              {clients.map((c) => (
                <option key={c.client_id} value={c.client_id}>
                  {c.company_name}
                </option>
              ))}
              {!lockClient && <option value={NEW_CLIENT}>＋ 신규 업체 직접 입력</option>}
            </select>
          </div>
          {clientId === NEW_CLIENT && (
            <div className="sm:col-span-2 grid gap-3 rounded-lg border border-emerald-400/25 bg-emerald-500/10 p-3 sm:grid-cols-[1fr_160px]">
              <div>
                <label className={labelCls}>
                  신규 업체명<span className="ml-0.5 text-rose-500">*</span>
                </label>
                <input
                  value={newCompanyName}
                  onChange={(e) => setNewCompanyName(e.target.value)}
                  className={inputCls}
                  placeholder="업체명 입력 — 상세 정보는 고객사 마스터에서 보완"
                  autoFocus
                />
              </div>
              <div>
                <label className={labelCls}>구분</label>
                <select
                  value={newClientType}
                  onChange={(e) => setNewClientType(e.target.value)}
                  className={inputCls}
                >
                  {clientTypeOptions.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}
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
              {activityTypeOptions.map((t) => (
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
          <div className="grid gap-3 rounded-lg border border-rose-400/25 bg-rose-500/10 p-3 sm:grid-cols-3">
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
            className="w-full rounded-lg border border-hairline bg-graphite px-3 py-2 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
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

        {/* 현장 사진 첨부 — 태블릿(pointer: coarse)에서 카메라 촬영 지원 */}
        <div>
          <label className={labelCls}>현장 사진 첨부</label>
          <FileUploader
            file={null}
            onChange={(f) => f && setPhotos((prev) => [...prev, f])}
            accept="image/*"
            enableCamera
            compressImages
          />
          {photos.length > 0 && (
            <ul className="mt-2 space-y-1.5">
              {photos.map((p, i) => (
                <li
                  key={`${p.name}-${i}`}
                  className="flex items-center gap-2.5 rounded-lg border border-hairline bg-elevate px-3 py-2"
                >
                  <FileImage size={18} className="shrink-0 text-smoke" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-bone">{p.name}</p>
                    <p className="text-xs text-slatey">{(p.size / 1024).toFixed(0)} KB</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setPhotos((prev) => prev.filter((_, j) => j !== i))}
                    className="rounded-md p-1 text-smoke hover:bg-elevate-strong hover:text-bone"
                    aria-label="사진 제거"
                  >
                    <X size={16} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

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
            등록
          </button>
        </div>
      </form>
    </Modal>
  )
}
