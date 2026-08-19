// SCR-06 상세 — 매수자별 선물 판매단가 거래계약 등록/수정.
// 매출 합계·차액은 서버 파생(매출=단가×수량 합) — 폼에서 수기 입력하지 않는다.
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { CircleNotch } from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { useToast } from '../../components/Toast'
import { useCodes } from '../../lib/api/queries'
import type { ProjectSale, ProjectSalePayload } from '../../types'
import { useBuyerOptions } from '../buyers/api'
import { useSaveSale } from './api'

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
  sale?: ProjectSale | null
}

export function SaleFormModal({ open, onClose, projectId, sale }: Props) {
  const { showToast } = useToast()
  const { options: buyerTypeOptions } = useCodes('SALE_BUYER_TYPE')
  const { data: buyers = [] } = useBuyerOptions()
  const save = useSaveSale(projectId, sale?.sale_id)

  const [form, setForm] = useState<ProjectSalePayload>({ buyer_name: '' })
  useEffect(() => {
    if (open) setForm(sale ? { ...sale } : { buyer_name: '' })
  }, [open, sale])

  const set = (k: keyof ProjectSalePayload, v: unknown) =>
    setForm((prev) => ({ ...prev, [k]: v }))

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await save.mutateAsync(form)
      showToast(sale ? '거래계약이 수정되었습니다.' : '거래계약이 등록되었습니다.', 'success')
      onClose()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail || '저장에 실패했습니다.', 'danger')
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={sale ? '거래계약 수정' : '거래계약 추가'} size="lg">
      <form onSubmit={submit} className="max-h-[70vh] space-y-4 overflow-y-auto pr-1">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="매수자 (마스터)">
            <select
              value={form.buyer_id ?? ''}
              onChange={(e) => {
                const v = e.target.value
                setForm((prev) => ({
                  ...prev,
                  buyer_id: v || null,
                  // 마스터 선택 시 표시·백엔드 유지용 buyer_name 동기화
                  buyer_name: v
                    ? (buyers.find((b) => b.buyer_id === v)?.name ?? prev.buyer_name)
                    : prev.buyer_name,
                }))
              }}
              className={inputCls}
            >
              <option value="">선택 안 함</option>
              {buyers.map((b) => (
                <option key={b.buyer_id} value={b.buyer_id}>
                  {b.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="매수자명(표시)">
            <input
              value={form.buyer_name ?? ''}
              onChange={(e) => set('buyer_name', e.target.value)}
              className={inputCls}
              placeholder="예: OO증권"
              required
            />
          </Field>
          <Field label="매수자 구분">
            <select
              value={form.buyer_type ?? ''}
              onChange={(e) => set('buyer_type', e.target.value || null)}
              className={inputCls}
            >
              <option value="">선택 안 함</option>
              {buyerTypeOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="선물 단가 (원/tCO₂)">
            <input
              type="number"
              min={0}
              value={form.sale_unit_price ?? ''}
              onChange={(e) => set('sale_unit_price', numOrNull(e.target.value))}
              className={inputCls}
            />
          </Field>
          <Field label="수량 (tCO₂)">
            <input
              type="number"
              min={0}
              step="0.001"
              value={form.quantity ?? ''}
              onChange={(e) => set('quantity', numOrNull(e.target.value))}
              className={inputCls}
            />
          </Field>
          <Field label="계약일">
            <input
              type="date"
              value={form.contract_date ?? ''}
              onChange={(e) => set('contract_date', e.target.value || null)}
              className={inputCls}
            />
          </Field>
          {/* ── P·B 회계 원장층 확장 — 매출인식·소유권·후시보유 ── */}
          <Field label="매출세금계산서 실발행액 (원)">
            <input
              type="number"
              min={0}
              value={form.sale_invoice_amount ?? ''}
              onChange={(e) => set('sale_invoice_amount', numOrNull(e.target.value))}
              className={inputCls}
            />
          </Field>
          <Field label="매출세금계산서 발행일">
            <input
              type="date"
              value={form.sale_invoice_date ?? ''}
              onChange={(e) => set('sale_invoice_date', e.target.value || null)}
              className={inputCls}
            />
          </Field>
          <Field label="매출세금계산서 입금일자">
            <input
              type="date"
              value={form.sale_payment_date ?? ''}
              onChange={(e) => set('sale_payment_date', e.target.value || null)}
              className={inputCls}
            />
          </Field>
          <Field label="소유권비율 (%)">
            <input
              type="number"
              min={0}
              max={100}
              step="0.01"
              value={form.ownership_pct ?? ''}
              onChange={(e) => set('ownership_pct', numOrNull(e.target.value))}
              className={inputCls}
            />
          </Field>
          <Field label="후시보유">
            <label className="flex h-10 items-center gap-2 text-sm text-bone">
              <input
                type="checkbox"
                checked={form.is_hold === 'Y'}
                onChange={(e) => set('is_hold', e.target.checked ? 'Y' : 'N')}
                className="h-4 w-4 rounded border-hairline bg-graphite accent-primary"
              />
              후시보유 대상
            </label>
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
            {sale ? '수정 저장' : '등록'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
