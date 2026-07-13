// SCR-06 사업 등록/수정 폼 — 고유번호 형식 검증, 발급완료 전환 시 확정 발급량 필수(R2-A1)
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { CircleNotch } from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { useToast } from '../../components/Toast'
import { useClientOptions, useUserOptions } from '../../lib/api/queries'
import { fmtDate } from '../../lib/format'
import type { Project, ProjectPayload } from '../../types'
import { MON_CYCLE_OPTIONS, PROJECT_STATUS_OPTIONS, useSaveProject } from './api'

const inputCls =
  'h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none'
const labelCls = 'mb-1 block text-xs font-medium text-ash'

// 고유번호 형식: R-YYYY-KR-03-NNNNNN (SCR-06 §5)
const REG_CODE_RE = /^R-\d{4}-KR-\d{2}-\d{6}$/

function Field({ label, required, children }: { label: string; required?: boolean; children: ReactNode }) {
  return (
    <div>
      <label className={labelCls}>
        {label}
        {required && <span className="ml-0.5 text-rose-500">*</span>}
      </label>
      {children}
    </div>
  )
}

interface FormState {
  client_id: string
  project_name: string
  reg_code: string
  project_status: string
  reg_date: string
  credit_start_date: string
  credit_end_date: string
  mon_start_date: string
  mon_end_date: string
  mon_cycle: string
  expected_issue_date: string
  expected_credits: string
  unit_price: string
  issued_credits: string
  issued_at: string
  manager_id: string
}

const toDate = (v?: string | null) => (v ? fmtDate(v) : '')

function initForm(project?: Project | null): FormState {
  return {
    client_id: project?.client_id ?? '',
    project_name: project?.project_name ?? '',
    reg_code: project?.reg_code ?? '',
    project_status: (project?.project_status as string) ?? '기획',
    reg_date: toDate(project?.reg_date),
    credit_start_date: toDate(project?.credit_start_date),
    credit_end_date: toDate(project?.credit_end_date),
    mon_start_date: toDate(project?.mon_start_date),
    mon_end_date: toDate(project?.mon_end_date),
    mon_cycle: project?.mon_cycle ?? '',
    expected_issue_date: toDate(project?.expected_issue_date),
    expected_credits: project?.expected_credits != null ? String(project.expected_credits) : '',
    unit_price: project?.unit_price != null ? String(project.unit_price) : '',
    issued_credits: project?.issued_credits != null ? String(project.issued_credits) : '',
    issued_at: toDate(project?.issued_at),
    manager_id: project?.manager_id ?? '',
  }
}

interface ProjectFormModalProps {
  open: boolean
  onClose: () => void
  /** 지정 시 수정 모드 */
  project?: Project | null
}

export function ProjectFormModal({ open, onClose, project }: ProjectFormModalProps) {
  const { showToast } = useToast()
  const { data: clients = [] } = useClientOptions()
  const { data: users = [] } = useUserOptions()
  const save = useSaveProject(project?.project_id)

  const [form, setForm] = useState<FormState>(() => initForm(project))

  useEffect(() => {
    if (open) setForm(initForm(project))
  }, [open, project])

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!form.project_name.trim()) {
      showToast('사업명을 입력해 주세요.', 'danger')
      return
    }
    if (!form.client_id) {
      showToast('대표 고객사를 선택해 주세요.', 'danger')
      return
    }
    if (!form.manager_id) {
      showToast('담당 PM을 선택해 주세요.', 'danger')
      return
    }
    if (form.reg_code.trim() && !REG_CODE_RE.test(form.reg_code.trim())) {
      showToast('고유번호 형식이 올바르지 않습니다. 예: R-2020-KR-03-000528', 'danger')
      return
    }
    // 발급완료 전환 게이트 — 확정 발급량·발급일 필수 (R2-A1)
    if (form.project_status === '발급완료' && (!form.issued_credits || !form.issued_at)) {
      showToast('발급완료 전환 시 확정 발급량과 발급일을 입력해야 합니다.', 'danger')
      return
    }

    const num = (v: string) => (v === '' ? null : Number(v))
    const payload: ProjectPayload = {
      client_id: form.client_id,
      project_name: form.project_name.trim(),
      reg_code: form.reg_code.trim() || null,
      project_status: form.project_status,
      reg_date: form.reg_date || null,
      credit_start_date: form.credit_start_date || null,
      credit_end_date: form.credit_end_date || null,
      mon_start_date: form.mon_start_date || null,
      mon_end_date: form.mon_end_date || null,
      mon_cycle: form.mon_cycle || null,
      expected_issue_date: form.expected_issue_date || null,
      expected_credits: num(form.expected_credits),
      unit_price: num(form.unit_price),
      issued_credits: form.project_status === '발급완료' ? num(form.issued_credits) : null,
      issued_at: form.project_status === '발급완료' ? form.issued_at || null : null,
      manager_id: form.manager_id,
    }

    try {
      await save.mutateAsync(payload)
      showToast(project ? '사업 정보가 수정되었습니다.' : '사업이 등록되었습니다.', 'success')
      onClose()
    } catch {
      showToast('저장에 실패했습니다. 잠시 후 다시 시도해 주세요.', 'danger')
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={project ? '사업 수정' : '신규 사업 등록'} size="lg">
      <form onSubmit={handleSubmit} className="max-h-[70vh] space-y-4 overflow-y-auto pr-1">
        {/* 기본 정보 */}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Field label="사업명" required>
              <input
                value={form.project_name}
                onChange={(e) => set('project_name', e.target.value)}
                className={inputCls}
                placeholder="예: 이우진 외 4농가 히트펌프 전환"
              />
            </Field>
          </div>
          <Field label="대표 고객사" required>
            <select
              value={form.client_id}
              onChange={(e) => set('client_id', e.target.value)}
              className={inputCls}
            >
              <option value="">선택</option>
              {clients.map((c) => (
                <option key={c.client_id} value={c.client_id}>
                  {c.company_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="고유번호">
            <input
              value={form.reg_code}
              onChange={(e) => set('reg_code', e.target.value)}
              className={`${inputCls} font-mono`}
              placeholder="R-2020-KR-03-000528"
            />
          </Field>
          <Field label="진행 상태" required>
            <select
              value={form.project_status}
              onChange={(e) => set('project_status', e.target.value)}
              className={inputCls}
            >
              {PROJECT_STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="등록일">
            <input
              type="date"
              value={form.reg_date}
              onChange={(e) => set('reg_date', e.target.value)}
              className={inputCls}
            />
          </Field>
        </div>

        {/* 발급완료 전환 게이트 (R2-A1) */}
        {form.project_status === '발급완료' && (
          <div className="rounded-lg border border-emerald-400/25 bg-emerald-500/15 p-3">
            <p className="mb-2 text-xs font-semibold text-emerald-300">
              발급완료 전환 — 확정 발급량·발급일 입력 필수
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="확정 발급량 (tCO₂)" required>
                <input
                  type="number"
                  min={0}
                  step="0.01"
                  value={form.issued_credits}
                  onChange={(e) => set('issued_credits', e.target.value)}
                  className={inputCls}
                />
              </Field>
              <Field label="발급일" required>
                <input
                  type="date"
                  value={form.issued_at}
                  onChange={(e) => set('issued_at', e.target.value)}
                  className={inputCls}
                />
              </Field>
            </div>
          </div>
        )}

        {/* 기간 */}
        <div className="border-t border-hairline pt-3">
          <p className="mb-2 text-xs font-semibold tracking-wider text-slatey uppercase">
            유효·모니터링 기간
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="유효기간 시작">
              <input
                type="date"
                value={form.credit_start_date}
                onChange={(e) => set('credit_start_date', e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="유효기간 종료">
              <input
                type="date"
                value={form.credit_end_date}
                onChange={(e) => set('credit_end_date', e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="모니터링 시작">
              <input
                type="date"
                value={form.mon_start_date}
                onChange={(e) => set('mon_start_date', e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="모니터링 종료">
              <input
                type="date"
                value={form.mon_end_date}
                onChange={(e) => set('mon_end_date', e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="모니터링 주기">
              <select
                value={form.mon_cycle}
                onChange={(e) => set('mon_cycle', e.target.value)}
                className={inputCls}
              >
                <option value="">선택</option>
                {MON_CYCLE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        </div>

        {/* 발급·단가 */}
        <div className="border-t border-hairline pt-3">
          <p className="mb-2 text-xs font-semibold tracking-wider text-slatey uppercase">
            배출권 발급·단가
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="예상 발급일">
              <input
                type="date"
                value={form.expected_issue_date}
                onChange={(e) => set('expected_issue_date', e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="예상 발행량 (tCO₂)">
              <input
                type="number"
                min={0}
                step="0.01"
                value={form.expected_credits}
                onChange={(e) => set('expected_credits', e.target.value)}
                className={inputCls}
                placeholder="예: 1500"
              />
            </Field>
            <Field label="배출권 단가 (원/tCO₂ — 미입력 시 정산액 미정)">
              <input
                type="number"
                min={0}
                value={form.unit_price}
                onChange={(e) => set('unit_price', e.target.value)}
                className={inputCls}
                placeholder="수기 입력 (§10.3)"
              />
            </Field>
            <Field label="담당 PM" required>
              <select
                value={form.manager_id}
                onChange={(e) => set('manager_id', e.target.value)}
                className={inputCls}
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

        {/* 액션 */}
        <div className="flex justify-end gap-2 border-t border-hairline pt-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-white/5"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={save.isPending}
            className="flex items-center gap-1.5 rounded-full bg-snow px-4 py-2 text-sm font-semibold text-graphite hover:bg-white/90 disabled:opacity-60"
          >
            {save.isPending && <CircleNotch size={14} className="animate-spin" />}
            {project ? '수정 저장' : '등록'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
