// SCR-14 기준값·매출단가 탭 (ADMIN 전용) — 감축 사업 파생 기준값 + 매출단가 시세 이력
// 기준값: tb_config project_base_params(JSON) 숫자 폼 — config API 재사용
// 매출단가: tb_market_rate effective-dated 이력 조회/등록 + 현재 시세 강조
import { useEffect, useMemo, useState } from 'react'
import { CurrencyKrw, Sliders } from '@phosphor-icons/react'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCards } from '../../components/Skeleton'
import { SensitiveData } from '../../components/SensitiveData'
import { useToast } from '../../components/Toast'
import { fmtMoney, fmtServerDate } from '../../lib/format'
import { useConfigList, useSaveConfig } from './api'
import {
  useCreateMarketRate,
  useCurrentRate,
  useMarketRates,
} from '../rates/api'

const BASE_PARAMS_KEY = 'project_base_params'

// 기준값 필드 정의 — 키·라벨·단위·정수 여부(백엔드는 양수만 검증, expire_months는 정수 개월)
const PARAM_FIELDS: {
  key: string
  label: string
  unit: string
  integer?: boolean
}[] = [
  { key: 'base_reduction', label: '기준감축량', unit: 'tCO2' },
  { key: 'base_vehicle_age', label: '기준차령', unit: '년' },
  { key: 'expire_months', label: '차령만료 개월', unit: '개월', integer: true },
  { key: 'default_max_payment', label: '차량당 기본 최대지급액', unit: '원', integer: true },
]

export function BaseParamsRatesTab() {
  return (
    <div className="space-y-6">
      <BaseParamsCard />
      <MarketRatesCard />
    </div>
  )
}

// ── 기준값 폼 (project_base_params) ──────────────────────────────────
function BaseParamsCard() {
  const { data: items, isLoading, isError, refetch } = useConfigList()
  const item = useMemo(
    () => items?.find((i) => i.key === BASE_PARAMS_KEY),
    [items],
  )

  if (isLoading) return <SkeletonCards count={1} />
  if (isError || !item) {
    return (
      <EmptyState
        icon={<Sliders size={36} />}
        title="기준값을 불러오지 못했습니다"
        description="감축 사업 기준값 설정을 불러오지 못했습니다. 잠시 후 다시 시도하세요."
        action={
          <button
            type="button"
            onClick={() => refetch()}
            className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
          >
            다시 시도
          </button>
        }
      />
    )
  }
  return <BaseParamsForm value={item.value} isDefault={item.is_default} />
}

function parseParams(value: string): Record<string, number> {
  try {
    const parsed = JSON.parse(value)
    if (parsed && typeof parsed === 'object') return parsed
  } catch {
    /* 파싱 실패 → 빈 객체(폼은 빈 값으로 시작) */
  }
  return {}
}

function BaseParamsForm({ value, isDefault }: { value: string; isDefault?: boolean }) {
  const { showToast } = useToast()
  const save = useSaveConfig()
  // 서버 값 → 문자열 드래프트(입력 편의). 저장 시 숫자 검증·직렬화.
  const toDraft = (v: string): Record<string, string> => {
    const obj = parseParams(v)
    const d: Record<string, string> = {}
    for (const f of PARAM_FIELDS) d[f.key] = obj[f.key] != null ? String(obj[f.key]) : ''
    return d
  }
  const [draft, setDraft] = useState<Record<string, string>>(() => toDraft(value))

  useEffect(() => {
    setDraft(toDraft(value))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  const invalid = PARAM_FIELDS.some((f) => {
    const raw = draft[f.key]?.trim()
    if (!raw) return true
    const n = Number(raw)
    return !Number.isFinite(n) || n <= 0
  })

  const handleSave = async () => {
    if (invalid) {
      showToast('모든 기준값은 0보다 큰 숫자여야 합니다.', 'danger')
      return
    }
    const payload: Record<string, number> = {}
    for (const f of PARAM_FIELDS) {
      const n = Number(draft[f.key])
      payload[f.key] = f.integer ? Math.round(n) : n
    }
    try {
      await save.mutateAsync({ key: BASE_PARAMS_KEY, value: JSON.stringify(payload) })
      showToast('기준값이 저장되었습니다.', 'success')
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      showToast(detail ?? '기준값 저장에 실패했습니다.', 'danger')
    }
  }

  return (
    <div className="rounded-3xl border border-hairline bg-graphite p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Sliders size={18} className="text-ash" />
        <h3 className="text-sm font-bold text-bone">감축 사업 기준값</h3>
        {isDefault && (
          <span className="inline-flex rounded-full border border-amber-400/25 bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:text-amber-300">
            기본값 (미저장)
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-slatey">
        예상지급액·잔여차령·차령만료일 계산의 기준값입니다. 저장 전에는 코드 기본값(현행)이
        적용됩니다.
      </p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {PARAM_FIELDS.map((f) => {
          const raw = draft[f.key]?.trim() ?? ''
          const fieldInvalid = !raw || !Number.isFinite(Number(raw)) || Number(raw) <= 0
          return (
            <label key={f.key} className="block">
              <span className="mb-1 block text-xs font-medium text-ash">
                {f.label} <span className="text-slatey">({f.unit})</span>
              </span>
              <input
                type="number"
                inputMode="decimal"
                value={draft[f.key] ?? ''}
                onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                className={`h-9 w-full rounded-lg border bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:outline-none ${
                  fieldInvalid
                    ? 'border-rose-400/40 focus:border-rose-400/60'
                    : 'border-hairline focus:border-white/30'
                }`}
              />
            </label>
          )
        })}
      </div>

      <div className="mt-4 flex justify-end border-t border-hairline pt-3">
        <button
          type="button"
          disabled={invalid || save.isPending}
          onClick={handleSave}
          className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {save.isPending ? '저장 중…' : '저장'}
        </button>
      </div>
    </div>
  )
}

// ── 매출단가 시세 이력 (tb_market_rate) ──────────────────────────────
function MarketRatesCard() {
  const { data: rates, isLoading, isError, refetch } = useMarketRates()
  const { data: current } = useCurrentRate()

  return (
    <div className="rounded-3xl border border-hairline bg-graphite p-5">
      <div className="flex flex-wrap items-center gap-2">
        <CurrencyKrw size={18} className="text-ash" />
        <h3 className="text-sm font-bold text-bone">매출단가 시세</h3>
        <span className="rounded-full border border-amber-400/25 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300">
          내부 전용
        </span>
      </div>
      <p className="mt-1 text-xs text-slatey">
        유효일자 기반 시세 이력입니다. 현재 시세는 유효일자 ≤ 오늘 중 가장 최신 단가이며,
        프로젝트 상세의 재고평가(후시보유분) 기준으로 쓰입니다.
      </p>

      {/* 현재 시세 강조 */}
      <div className="mt-3 rounded-2xl border border-hairline bg-elevate-strong px-4 py-3">
        <p className="text-[11px] font-medium text-slatey">현재 시세</p>
        {current ? (
          <p className="mt-0.5 text-sm font-bold text-bone">
            <SensitiveData type="money" value={fmtMoney(Number(current.unit_price))} /> 원/tCO2
            <span className="ml-2 text-xs font-normal text-slatey">
              (유효일자 {fmtServerDate(current.effective_date)})
            </span>
          </p>
        ) : (
          <p className="mt-0.5 text-xs font-medium text-amber-400">등록된 시세가 없습니다.</p>
        )}
      </div>

      <RateForm />

      {/* 이력 목록 */}
      <div className="mt-4">
        {isLoading ? (
          <p className="text-xs text-slatey">시세 이력을 불러오는 중…</p>
        ) : isError ? (
          <p className="flex items-center gap-2 text-xs text-rose-500">
            시세 이력을 불러오지 못했습니다.
            <button type="button" onClick={() => refetch()} className="underline">
              다시 시도
            </button>
          </p>
        ) : !rates || rates.length === 0 ? (
          <p className="text-xs text-slatey">등록된 시세 이력이 없습니다.</p>
        ) : (
          <div className="overflow-x-auto rounded-2xl border border-hairline">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hairline text-left text-xs text-slatey">
                  <th className="px-3 py-2 font-medium">유효일자</th>
                  <th className="px-3 py-2 text-right font-medium">단가 (원/tCO2)</th>
                  <th className="px-3 py-2 font-medium">비고</th>
                </tr>
              </thead>
              <tbody>
                {rates.map((r) => (
                  <tr key={r.rate_id} className="border-b border-hairline last:border-b-0">
                    <td className="px-3 py-2 text-ash">{fmtServerDate(r.effective_date)}</td>
                    <td className="px-3 py-2 text-right text-bone">
                      <SensitiveData type="money" value={fmtMoney(Number(r.unit_price))} />
                    </td>
                    <td className="px-3 py-2 text-slatey">{r.note || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ── 시세 등록 폼 ─────────────────────────────────────────────────────
function RateForm() {
  const { showToast } = useToast()
  const create = useCreateMarketRate()
  const [effectiveDate, setEffectiveDate] = useState('')
  const [unitPrice, setUnitPrice] = useState('')
  const [note, setNote] = useState('')

  const priceNum = Number(unitPrice)
  const valid = !!effectiveDate && !!unitPrice.trim() && Number.isFinite(priceNum) && priceNum >= 0

  const handleSubmit = async () => {
    if (!valid) {
      showToast('유효일자와 0 이상의 단가를 입력하세요.', 'danger')
      return
    }
    try {
      await create.mutateAsync({
        effective_date: effectiveDate,
        unit_price: priceNum,
        note: note.trim() || null,
      })
      showToast('시세가 등록되었습니다.', 'success')
      setEffectiveDate('')
      setUnitPrice('')
      setNote('')
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      showToast(detail ?? '시세 등록에 실패했습니다.', 'danger')
    }
  }

  return (
    <div className="mt-4 grid gap-2 border-t border-hairline pt-4 sm:grid-cols-[auto_auto_1fr_auto] sm:items-end">
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-ash">유효일자</span>
        <input
          type="date"
          value={effectiveDate}
          onChange={(e) => setEffectiveDate(e.target.value)}
          className="h-9 rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone focus:border-white/30 focus:outline-none"
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-ash">단가 (원/tCO2)</span>
        <input
          type="number"
          inputMode="decimal"
          value={unitPrice}
          onChange={(e) => setUnitPrice(e.target.value)}
          placeholder="예: 14000"
          className="h-9 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-ash">비고</span>
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="선택"
          className="h-9 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
        />
      </label>
      <button
        type="button"
        disabled={!valid || create.isPending}
        onClick={handleSubmit}
        className="h-9 rounded-full bg-primary px-4 text-sm font-medium text-on-primary hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {create.isPending ? '등록 중…' : '시세 등록'}
      </button>
    </div>
  )
}
