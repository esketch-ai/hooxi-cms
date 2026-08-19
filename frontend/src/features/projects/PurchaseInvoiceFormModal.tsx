// SCR-06 상세 — 매입세금계산서(P·B 회계 원장층) 등록/수정.
// 총매입(제품)은 서버 파생(발행액 합) — 폼에서 합계를 수기 입력하지 않는다.
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { CircleNotch } from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { useToast } from '../../components/Toast'
import type { PurchaseInvoice, PurchaseInvoicePayload } from '../../types'
import { useCodes } from '../../lib/api/queries'
import { useSavePurchaseInvoice } from './api'

const inputCls =
  'h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none'
const labelCls = 'mb-1 block text-xs font-medium text-ash'

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <label className={labelCls}>{label}</label>
      {children}
    </div>
  )
}

const numOrNull = (v: string) => (v === '' ? null : Number(v))

interface Props {
  open: boolean
  onClose: () => void
  projectId: string
  invoice?: PurchaseInvoice | null
}

export function PurchaseInvoiceFormModal({ open, onClose, projectId, invoice }: Props) {
  const { showToast } = useToast()
  const save = useSavePurchaseInvoice(projectId, invoice?.invoice_id)
  const { options: regionOptions = [] } = useCodes('REGION')

  const [form, setForm] = useState<PurchaseInvoicePayload>({ amount: 0 })
  useEffect(() => {
    if (open) setForm(invoice ? { ...invoice } : { amount: 0 })
  }, [open, invoice])

  const set = (k: keyof PurchaseInvoicePayload, v: unknown) =>
    setForm((prev) => ({ ...prev, [k]: v }))

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await save.mutateAsync(form)
      showToast(
        invoice ? '매입세금계산서가 수정되었습니다.' : '매입세금계산서가 등록되었습니다.',
        'success',
      )
      onClose()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail || '저장에 실패했습니다.', 'danger')
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={invoice ? '매입세금계산서 수정' : '매입세금계산서 추가'}
      size="lg"
    >
      <form onSubmit={submit} className="max-h-[70vh] space-y-4 overflow-y-auto pr-1">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="운수사명">
            <input
              value={form.operator_name ?? ''}
              onChange={(e) => set('operator_name', e.target.value || null)}
              className={inputCls}
              placeholder="예: OO운수"
            />
          </Field>
          <Field label="지역">
            <select
              value={form.region ?? ''}
              onChange={(e) => set('region', e.target.value || null)}
              className={inputCls}
            >
              <option value="">선택 안 함</option>
              {regionOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="발행일">
            <input
              type="date"
              value={form.issue_date ?? ''}
              onChange={(e) => set('issue_date', e.target.value || null)}
              className={inputCls}
            />
          </Field>
          <Field label="입금일자">
            <input
              type="date"
              value={form.payment_date ?? ''}
              onChange={(e) => set('payment_date', e.target.value || null)}
              className={inputCls}
            />
          </Field>
          <Field label="금액 (원)">
            <input
              type="number"
              min={0}
              value={form.amount ?? ''}
              onChange={(e) => set('amount', numOrNull(e.target.value))}
              className={inputCls}
              required
            />
          </Field>
          <Field label="비고">
            <input
              value={form.memo ?? ''}
              onChange={(e) => set('memo', e.target.value || null)}
              className={inputCls}
            />
          </Field>
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
            disabled={save.isPending}
            className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-60"
          >
            {save.isPending && <CircleNotch size={14} className="animate-spin" />}
            {invoice ? '수정 저장' : '등록'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
