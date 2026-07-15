// SCR-03 고객사 등록/수정 폼 — 플랜 §5 필드 목록 + 월간 보고서 설정 섹션
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { CircleNotch } from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { useToast } from '../../components/Toast'
import { useCodes, useUserOptions } from '../../lib/api/queries'
import { fmtDate } from '../../lib/format'
import type { Client, ClientPayload, ClientType, ContractStatus } from '../../types'
import { useSaveClient } from './api'

const inputCls =
  'h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none'
// 검증 실패 필드 — 빨간 테두리 (L-1 인라인 검증)
const inputErrorCls =
  'h-10 w-full rounded-lg border border-rose-400/50 bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-rose-400 focus:outline-none'
const labelCls = 'mb-1 block text-xs font-medium text-ash'

function Field({
  label,
  required,
  error,
  children,
}: {
  label: string
  required?: boolean
  /** 인라인 에러 텍스트 — 존재 시 필드 아래 표시 */
  error?: string
  children: ReactNode
}) {
  return (
    <div>
      <label className={labelCls}>
        {label}
        {required && <span className="ml-0.5 text-rose-500">*</span>}
      </label>
      {children}
      {error && <p className="mt-1 text-xs text-rose-500">{error}</p>}
    </div>
  )
}

interface ClientFormModalProps {
  open: boolean
  onClose: () => void
  /** 지정 시 수정 모드 */
  client?: Client | null
}

export function ClientFormModal({ open, onClose, client }: ClientFormModalProps) {
  const { showToast } = useToast()
  const { data: users = [] } = useUserOptions()
  const { options: clientTypeOptions } = useCodes('CLIENT_TYPE')
  const { options: contractStatusOptions } = useCodes('CONTRACT_STATUS')
  const save = useSaveClient(client?.client_id)

  const [form, setForm] = useState<ClientPayload>(() => initForm(client))
  // 월간 보고서 설정 (tb_report_subscription — 중첩 subscription payload)
  const [subType, setSubType] = useState('')
  const [subChannel, setSubChannel] = useState<'EMAIL' | 'KAKAO' | 'BOTH'>('EMAIL')
  const [subDueDay, setSubDueDay] = useState<number | null>(null)
  // 메일 제목/본문 커스텀 (선택) — 비우면 전역 기본 템플릿(tb_config) 사용
  const [subMailSubject, setSubMailSubject] = useState('')
  const [subMailBody, setSubMailBody] = useState('')
  // 인라인 검증 에러 (L-1) — key: ClientPayload 키 또는 'subType'
  const [errors, setErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    if (open) {
      setForm(initForm(client))
      const sub = client?.subscriptions?.[0]
      setSubType(sub?.report_type ?? '')
      setSubChannel((sub?.channel as 'EMAIL' | 'KAKAO' | 'BOTH') ?? 'EMAIL')
      setSubDueDay(sub?.due_day ?? null)
      setSubMailSubject(sub?.mail_subject ?? '')
      setSubMailBody(sub?.mail_body ?? '')
      setErrors({})
    }
  }, [open, client])

  const clearError = (key: string) =>
    setErrors((prev) => {
      if (!prev[key]) return prev
      const next = { ...prev }
      delete next[key]
      return next
    })

  const set = <K extends keyof ClientPayload>(key: K, value: ClientPayload[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    clearError(key) // 입력 시 인라인 에러 해제
  }

  /** 검증 실패 필드는 빨간 테두리 */
  const fieldCls = (key: string) => (errors[key] ? inputErrorCls : inputCls)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    // 필수 검증 (플랜 §5 SCR-03: 구분·고객사명·사업자번호·주소·대표자명·대표 연락처·주 담당자명·연락처·이메일·계약 상태·담당 PM)
    const required: [keyof ClientPayload, string][] = [
      ['company_name', '고객사명'],
      ['biz_reg_no', '사업자번호'],
      ['address', '주소'],
      ['ceo_name', '대표자명'],
      ['ceo_contact_phone', '대표 연락처'],
      ['main_contact_name', '주 담당자명'],
      ['main_contact_phone', '주 담당자 연락처'],
      ['main_contact_email', '주 담당자 이메일'],
      ['manager_id', '담당 PM'],
    ]
    // 누락 필수 필드 전체 수집 → 인라인 표시 (L-1)
    const nextErrors: Record<string, string> = {}
    for (const [key, label] of required) {
      if (!String(form[key] ?? '').trim()) {
        nextErrors[key] = `${label}을(를) 입력해 주세요.`
      }
    }
    if (form.report_yn === 'Y' && !subType.trim()) {
      nextErrors.subType = '보고서 수신 시 보고서 유형을 입력해 주세요.'
    }
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors)
      showToast('필수 항목을 입력해 주세요.', 'danger')
      return
    }
    setErrors({})
    try {
      await save.mutateAsync({
        ...form,
        contract_date: form.contract_date || null,
        subscription:
          form.report_yn === 'Y' && subType.trim()
            ? {
                report_type: subType.trim(),
                channel: subChannel,
                due_day: subDueDay,
                active: 'Y',
                // 빈 문자열은 null(= 전역 기본 템플릿 사용)로 정규화
                mail_subject: subMailSubject.trim() || null,
                mail_body: subMailBody.trim() || null,
              }
            : undefined,
      })
      showToast(client ? '고객사 정보가 수정되었습니다.' : '고객사가 등록되었습니다.', 'success')
      onClose()
    } catch {
      showToast('저장에 실패했습니다. 잠시 후 다시 시도해 주세요.', 'danger')
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={client ? '고객사 수정' : '신규 고객사 등록'}
      size="lg"
    >
      <form onSubmit={handleSubmit} className="max-h-[70vh] space-y-4 overflow-y-auto pr-1">
        {/* 기본 정보 */}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="구분" required>
            <select
              value={form.client_type}
              onChange={(e) => set('client_type', e.target.value as ClientType)}
              className={inputCls}
            >
              {/* 기존 값이 비활성 코드라도 선택 상태가 유지되도록 폴백 옵션 노출 */}
              {form.client_type &&
                !clientTypeOptions.some((o) => o.value === form.client_type) && (
                  <option value={form.client_type}>{form.client_type}</option>
                )}
              {clientTypeOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="고객사명" required error={errors.company_name}>
            <input
              value={form.company_name}
              onChange={(e) => set('company_name', e.target.value)}
              className={fieldCls('company_name')}
              placeholder="예: 대성운수"
            />
          </Field>
          <Field label="사업자번호" required error={errors.biz_reg_no}>
            <input
              value={form.biz_reg_no ?? ''}
              onChange={(e) => set('biz_reg_no', e.target.value)}
              className={fieldCls('biz_reg_no')}
              placeholder="000-00-00000"
            />
          </Field>
          <Field label="지역">
            <input
              value={form.region ?? ''}
              onChange={(e) => set('region', e.target.value)}
              className={inputCls}
              placeholder="예: 서울"
            />
          </Field>
          <div className="sm:col-span-2">
            <Field label="주소" required error={errors.address}>
              <input
                value={form.address ?? ''}
                onChange={(e) => set('address', e.target.value)}
                className={fieldCls('address')}
              />
            </Field>
          </div>
          <Field label="대표자명" required error={errors.ceo_name}>
            <input
              value={form.ceo_name ?? ''}
              onChange={(e) => set('ceo_name', e.target.value)}
              className={fieldCls('ceo_name')}
            />
          </Field>
          <Field label="대표 연락처" required error={errors.ceo_contact_phone}>
            <input
              value={form.ceo_contact_phone ?? ''}
              onChange={(e) => set('ceo_contact_phone', e.target.value)}
              className={fieldCls('ceo_contact_phone')}
              placeholder="02-0000-0000"
            />
          </Field>
          <Field label="대표 이메일">
            <input
              type="email"
              value={form.ceo_contact_email ?? ''}
              onChange={(e) => set('ceo_contact_email', e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label="keyman (주요 결정권자)">
            <input
              value={form.keyman ?? ''}
              onChange={(e) => set('keyman', e.target.value)}
              className={inputCls}
            />
          </Field>
        </div>

        {/* 주 담당자 (고객사측) */}
        <div className="border-t border-hairline pt-3">
          <p className="mb-2 text-xs font-semibold tracking-wider text-slatey uppercase">
            고객사 주 담당자
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="주 담당자명" required error={errors.main_contact_name}>
              <input
                value={form.main_contact_name ?? ''}
                onChange={(e) => set('main_contact_name', e.target.value)}
                className={fieldCls('main_contact_name')}
              />
            </Field>
            <Field label="연락처 (카카오 매핑 기준)" required error={errors.main_contact_phone}>
              <input
                value={form.main_contact_phone ?? ''}
                onChange={(e) => set('main_contact_phone', e.target.value)}
                className={fieldCls('main_contact_phone')}
                placeholder="010-0000-0000"
              />
            </Field>
            <Field label="이메일 (보고서 발송 기준)" required error={errors.main_contact_email}>
              <input
                type="email"
                value={form.main_contact_email ?? ''}
                onChange={(e) => set('main_contact_email', e.target.value)}
                className={fieldCls('main_contact_email')}
              />
            </Field>
          </div>
        </div>

        {/* 계약·담당 */}
        <div className="border-t border-hairline pt-3">
          <p className="mb-2 text-xs font-semibold tracking-wider text-slatey uppercase">
            계약·담당
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="계약 상태" required>
              <select
                value={form.contract_status}
                onChange={(e) => set('contract_status', e.target.value as ContractStatus)}
                className={inputCls}
              >
                {form.contract_status &&
                  !contractStatusOptions.some((o) => o.value === form.contract_status) && (
                    <option value={form.contract_status}>{form.contract_status}</option>
                  )}
                {contractStatusOptions.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="계약 일자">
              <input
                type="date"
                value={form.contract_date ?? ''}
                onChange={(e) => set('contract_date', e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="담당 PM" required error={errors.manager_id}>
              <select
                value={form.manager_id ?? ''}
                onChange={(e) => set('manager_id', e.target.value)}
                className={fieldCls('manager_id')}
              >
                <option value="">선택</option>
                {users.map((u) => (
                  <option key={u.user_id} value={u.user_id}>
                    {u.name} {u.position ? `(${u.position})` : ''}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        </div>

        {/* 월간 보고서 설정 (tb_report_subscription) */}
        <div className="border-t border-hairline pt-3">
          <p className="mb-2 text-xs font-semibold tracking-wider text-slatey uppercase">
            월간 보고서 설정
          </p>
          <div className="grid gap-3 sm:grid-cols-4">
            <Field label="수신 여부">
              <select
                value={form.report_yn ?? 'N'}
                onChange={(e) => {
                  set('report_yn', e.target.value)
                  if (e.target.value !== 'Y') clearError('subType')
                }}
                className={inputCls}
              >
                <option value="Y">수신 (Y)</option>
                <option value="N">미수신 (N)</option>
              </select>
            </Field>
            <Field label="보고서 유형" error={errors.subType}>
              <input
                value={subType}
                onChange={(e) => {
                  setSubType(e.target.value)
                  clearError('subType')
                }}
                className={fieldCls('subType')}
                placeholder="예: 월간 운행 보고서"
                disabled={form.report_yn !== 'Y'}
              />
            </Field>
            <Field label="발송 채널">
              <select
                value={subChannel}
                onChange={(e) => setSubChannel(e.target.value as 'EMAIL' | 'KAKAO' | 'BOTH')}
                className={inputCls}
                disabled={form.report_yn !== 'Y'}
              >
                <option value="EMAIL">이메일</option>
                <option value="KAKAO">카카오</option>
                <option value="BOTH">이메일+카카오</option>
              </select>
            </Field>
            <Field label="마감일 (매월 n일)">
              <input
                type="number"
                min={1}
                max={31}
                value={subDueDay ?? ''}
                onChange={(e) => setSubDueDay(e.target.value ? Number(e.target.value) : null)}
                className={inputCls}
                disabled={form.report_yn !== 'Y'}
              />
            </Field>
          </div>
          {/* 메일 제목/본문 커스텀 (선택) — 비우면 전역 기본 템플릿(시스템 설정) 사용 */}
          <div className="mt-3 space-y-3">
            <Field label="메일 제목 커스텀 (선택 — 비우면 기본 템플릿)">
              <input
                value={subMailSubject}
                onChange={(e) => setSubMailSubject(e.target.value)}
                className={inputCls}
                placeholder="예: [흑시파트너스] {고객사명} {기간} {보고서유형} 송부드립니다"
                disabled={form.report_yn !== 'Y'}
              />
            </Field>
            <Field label="메일 본문 커스텀 (선택 — 비우면 기본 템플릿)">
              <textarea
                value={subMailBody}
                onChange={(e) => setSubMailBody(e.target.value)}
                rows={5}
                className="w-full rounded-lg border border-hairline bg-graphite px-3 py-2 text-sm leading-relaxed text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none disabled:opacity-50"
                placeholder={'예: {고객사명} 담당자님, 안녕하세요.\n{기간} {보고서유형}을 첨부와 같이 송부드립니다.'}
                disabled={form.report_yn !== 'Y'}
              />
            </Field>
            <p className="text-[11px] text-slatey">
              치환 변수: {'{고객사명} {기간} {연도} {월} {보고서유형} {담당자명}'} — 배치·수동
              발송 메일에 적용됩니다.
            </p>
          </div>
        </div>

        {/* 액션 */}
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
            disabled={save.isPending}
            className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-60"
          >
            {save.isPending && <CircleNotch size={14} className="animate-spin" />}
            {client ? '수정 저장' : '등록'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function initForm(client?: Client | null): ClientPayload {
  return {
    client_type: client?.client_type ?? 'TRANSPORT',
    company_name: client?.company_name ?? '',
    biz_reg_no: client?.biz_reg_no ?? '',
    region: client?.region ?? '',
    address: client?.address ?? '',
    ceo_name: client?.ceo_name ?? '',
    ceo_contact_phone: client?.ceo_contact_phone ?? '',
    ceo_contact_email: client?.ceo_contact_email ?? '',
    main_contact_name: client?.main_contact_name ?? '',
    main_contact_phone: client?.main_contact_phone ?? '',
    main_contact_email: client?.main_contact_email ?? '',
    contract_status: client?.contract_status ?? 'ACTIVE',
    contract_date: client?.contract_date ? fmtDate(client.contract_date) : '',
    keyman: client?.keyman ?? '',
    manager_id: client?.manager_id ?? '',
    report_yn: client?.report_yn ?? 'N',
  }
}
