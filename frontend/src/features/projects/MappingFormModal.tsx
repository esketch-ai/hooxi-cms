// SCR-06 상세 — 참여 고객사 매핑 추가/수정 폼 (배분율 합계 100% 초과 시 저장 차단)
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { CircleNotch, Warning } from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { useToast } from '../../components/Toast'
import { useClientOptions } from '../../lib/api/queries'
import { useClientAssets } from '../clients/api'
import type { MappingPayload, ProjectClientMap } from '../../types'
import { useSaveMapping } from './api'

const inputCls =
  'h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none'
const labelCls = 'mb-1 block text-xs font-medium text-ash'

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

interface MappingFormModalProps {
  open: boolean
  onClose: () => void
  projectId: string
  /** 지정 시 수정 모드 */
  mapping?: ProjectClientMap | null
  /** 전체 매핑 목록 — 배분율 합계 검증용 */
  mappings: ProjectClientMap[]
}

export function MappingFormModal({ open, onClose, projectId, mapping, mappings }: MappingFormModalProps) {
  const { showToast } = useToast()
  const { data: clients = [] } = useClientOptions()
  // 동일 고객사 POST = upsert (routers/projects.py) — 수정도 같은 엔드포인트
  const save = useSaveMapping(projectId)

  const [clientId, setClientId] = useState('')
  const [assetId, setAssetId] = useState('')
  const [ratio, setRatio] = useState('')
  const [feeRate, setFeeRate] = useState('')

  // 선택 고객사의 자산만 연결 후보 (SCR-06 §4.2)
  const { data: clientAssets = [] } = useClientAssets(clientId || undefined)

  useEffect(() => {
    if (open) {
      setClientId(mapping?.client_id ?? '')
      setAssetId(mapping?.asset_id ?? '')
      setRatio(mapping?.allocation_ratio != null ? String(mapping.allocation_ratio) : '')
      setFeeRate(mapping?.success_fee_rate != null ? String(mapping.success_fee_rate) : '')
    }
  }, [open, mapping])

  // 본 건 제외 나머지 배분율 합계
  const otherSum = useMemo(
    () =>
      mappings
        .filter((m) => m.map_id !== mapping?.map_id)
        .reduce((acc, m) => acc + (Number(m.allocation_ratio) || 0), 0),
    [mappings, mapping],
  )
  const nextSum = otherSum + (Number(ratio) || 0)
  const exceeds = nextSum > 100

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!clientId) {
      showToast('참여 고객사를 선택해 주세요.', 'danger')
      return
    }
    if (ratio === '' || Number(ratio) <= 0) {
      showToast('배분율을 입력해 주세요.', 'danger')
      return
    }
    if (feeRate === '' || Number(feeRate) < 0) {
      showToast('성공 보수율을 입력해 주세요.', 'danger')
      return
    }
    if (exceeds) {
      showToast(`배분율 합계가 100%를 초과합니다. (현재 ${nextSum.toFixed(1)}%)`, 'danger')
      return
    }

    const payload: MappingPayload = {
      client_id: clientId,
      asset_id: assetId || null,
      allocation_ratio: Number(ratio),
      success_fee_rate: Number(feeRate),
    }
    try {
      await save.mutateAsync(payload)
      showToast(mapping ? '매핑이 수정되었습니다.' : '참여 고객사가 추가되었습니다.', 'success')
      onClose()
    } catch {
      showToast('저장에 실패했습니다. 잠시 후 다시 시도해 주세요.', 'danger')
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={mapping ? '참여 고객사 매핑 수정' : '참여 고객사 추가'}
      size="md"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="참여 고객사" required>
            <select
              value={clientId}
              onChange={(e) => {
                setClientId(e.target.value)
                setAssetId('') // 고객사 변경 시 자산 선택 초기화
              }}
              className={inputCls}
              disabled={!!mapping}
            >
              <option value="">선택</option>
              {clients.map((c) => (
                <option key={c.client_id} value={c.client_id}>
                  {c.company_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="연결 자산">
            <select
              value={assetId}
              onChange={(e) => setAssetId(e.target.value)}
              className={inputCls}
              disabled={!clientId}
            >
              <option value="">{clientId ? '선택 안 함' : '고객사 먼저 선택'}</option>
              {clientAssets.map((a) => (
                <option key={a.asset_id} value={a.asset_id}>
                  {[a.asset_type, a.main_spec, a.quantity != null ? `${a.quantity}대` : null]
                    .filter(Boolean)
                    .join(' · ')}
                </option>
              ))}
            </select>
          </Field>
          <Field label="배분율 (%)" required>
            <input
              type="number"
              min={0}
              max={100}
              step="0.1"
              value={ratio}
              onChange={(e) => setRatio(e.target.value)}
              className={inputCls}
              placeholder="예: 20"
            />
          </Field>
          <Field label="성공 보수율 (%)" required>
            <input
              type="number"
              min={0}
              max={100}
              step="0.1"
              value={feeRate}
              onChange={(e) => setFeeRate(e.target.value)}
              className={inputCls}
              placeholder="예: 15"
            />
          </Field>
        </div>

        {/* 배분율 합계 미리보기 — 100% 초과 시 저장 차단 */}
        <div
          className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${
            exceeds
              ? 'border-rose-400/25 bg-rose-500/15 text-rose-700 dark:text-rose-300'
              : 'border-hairline bg-elevate text-ash'
          }`}
        >
          {exceeds && <Warning size={14} weight="fill" />}
          저장 후 배분율 합계: <span className="font-bold">{nextSum.toFixed(1)}%</span>
          {exceeds && ' — 100%를 초과하여 저장할 수 없습니다.'}
        </div>

        <p className="text-xs text-slatey">
          예상 정산액은 발급량 × 배분율 × 단가 × 보수율로 서버가 자동 계산합니다. 단가 미입력 시
          &ldquo;미정&rdquo;으로 표시됩니다.
        </p>

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
            disabled={save.isPending || exceeds}
            className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-60"
          >
            {save.isPending && <CircleNotch size={14} className="animate-spin" />}
            {mapping ? '수정 저장' : '추가'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
