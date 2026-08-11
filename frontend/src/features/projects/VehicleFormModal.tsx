// SCR-06 상세 — 사업 참여 차량 등록/수정 (Phase 2). 연차(1~10) 감축량·도입구분·민간투자비율 ingest.
// 예상지급액은 원가 톤당 단가×총감축량 서버 파생(H.4) — 폼에서 수기 입력하지 않는다.
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { CircleNotch } from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { useToast } from '../../components/Toast'
import { useClientOptions, useCodes } from '../../lib/api/queries'
import type { ProjectVehicle, ProjectVehiclePayload } from '../../types'
import { useSaveVehicle } from './api'

const inputCls =
  'h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none'
const smallInput =
  'h-9 w-full rounded-md border border-hairline bg-graphite px-2 text-xs text-bone focus:border-white/30 focus:outline-none'
const labelCls = 'mb-1 block text-xs font-medium text-ash'

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <label className={labelCls}>{label}</label>
      {children}
    </div>
  )
}

const YEARS = Array.from({ length: 10 }, (_, i) => i + 1)
const numOrNull = (v: string) => (v === '' ? null : Number(v))

interface Props {
  open: boolean
  onClose: () => void
  projectId: string
  vehicle?: ProjectVehicle | null
}

export function VehicleFormModal({ open, onClose, projectId, vehicle }: Props) {
  const { showToast } = useToast()
  const { options: introOptions } = useCodes('VEHICLE_INTRO')
  const { options: regionOptions } = useCodes('REGION')
  const { data: clients = [] } = useClientOptions()
  const save = useSaveVehicle(projectId, vehicle?.vehicle_id)

  const [form, setForm] = useState<ProjectVehiclePayload>({})
  useEffect(() => {
    if (open) setForm(vehicle ? { ...vehicle } : {})
  }, [open, vehicle])

  const set = (k: keyof ProjectVehiclePayload, v: unknown) =>
    setForm((prev) => ({ ...prev, [k]: v }))

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await save.mutateAsync(form)
      showToast(vehicle ? '차량 정보가 수정되었습니다.' : '차량이 등록되었습니다.', 'success')
      onClose()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail || '저장에 실패했습니다.', 'danger')
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={vehicle ? '차량 수정' : '차량 등록'} size="lg">
      <form onSubmit={submit} className="max-h-[70vh] space-y-4 overflow-y-auto pr-1">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="차량번호">
            <input
              value={form.vehicle_no ?? ''}
              onChange={(e) => set('vehicle_no', e.target.value)}
              className={inputCls}
              placeholder="예: 제주79자7011"
            />
          </Field>
          <Field label="운수사">
            <select
              value={form.client_id ?? ''}
              onChange={(e) => set('client_id', e.target.value || null)}
              className={inputCls}
            >
              <option value="">선택 안 함</option>
              {clients.map((c) => (
                <option key={c.client_id} value={c.client_id}>
                  {c.company_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="도입구분">
            <select
              value={form.introduction_type ?? ''}
              onChange={(e) => set('introduction_type', e.target.value || null)}
              className={inputCls}
            >
              <option value="">선택 안 함</option>
              {introOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="지역 (시/도)">
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
          <Field label="차량등록일">
            <input
              type="date"
              value={form.registered_at ?? ''}
              onChange={(e) => set('registered_at', e.target.value || null)}
              className={inputCls}
            />
          </Field>
          <Field label="민간투자비율 (%)">
            <input
              type="number"
              min={0}
              max={100}
              value={form.private_invest_ratio ?? ''}
              onChange={(e) => set('private_invest_ratio', numOrNull(e.target.value))}
              className={inputCls}
            />
          </Field>
        </div>

        {/* 연차 감축량 (1~10차) — 방법론 산정 결과 입력(부록 G) */}
        <div>
          <p className="mb-2 text-xs font-semibold tracking-wider text-slatey uppercase">
            연차 감축량 (tCO₂) — 1~10차
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {YEARS.map((y) => {
              const key = `reduction_y${y}` as keyof ProjectVehiclePayload
              return (
                <div key={y}>
                  <label className="mb-0.5 block text-[10px] text-slatey">{y}차</label>
                  <input
                    type="number"
                    min={0}
                    step="0.001"
                    value={(form[key] as number | null | undefined) ?? ''}
                    onChange={(e) => set(key, numOrNull(e.target.value))}
                    className={smallInput}
                  />
                </div>
              )
            })}
          </div>
        </div>

        <div className="grid gap-3">
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
            {vehicle ? '수정 저장' : '등록'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
