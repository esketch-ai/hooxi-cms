// SCR-04 자산 등록/수정 폼 — 인증 방식별 필드 동적 표시, 인증 정보는 입력 시에만 전송
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { CircleNotch } from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { useToast } from '../../components/Toast'
import { useClientOptions, useCodes } from '../../lib/api/queries'
import type { Asset, AssetPayload } from '../../types'
import { useSaveAsset } from './api'

const inputCls =
  'h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none'
const labelCls = 'mb-1 block text-xs font-medium text-ash'

function Field({ label, required, children }: { label: string; required?: boolean; children: ReactNode }) {
  return (
    <div>
      <label className={labelCls}>
        {label}
        {required && <span className="ml-0.5 text-rose-400">*</span>}
      </label>
      {children}
    </div>
  )
}

interface FormState {
  client_id: string
  asset_group: string
  asset_type: string
  quantity: string
  main_spec: string
  telemetry_yn: string
  location_info: string
  status: string
  agency_name: string
  site_url: string
  auth_type: string
  login_id: string
  auth_secret: string // PW 또는 API 토큰 — 입력 시에만 전송
  usage_purpose: string
}

function initForm(asset?: Asset | null): FormState {
  return {
    client_id: asset?.client_id ?? '',
    asset_group: asset?.asset_group ?? 'MOBILITY',
    asset_type: asset?.asset_type ?? 'ICE',
    quantity: asset?.quantity != null ? String(asset.quantity) : '',
    main_spec: asset?.main_spec ?? '',
    telemetry_yn: asset?.telemetry_yn ?? 'N',
    location_info: asset?.location_info ?? '',
    status: asset?.status ?? 'ACTIVE',
    agency_name: asset?.agency_name ?? '',
    site_url: asset?.site_url ?? '',
    auth_type: asset?.auth_type ?? 'NONE',
    login_id: asset?.login_id ?? '',
    auth_secret: '', // 저장 후 재조회 불가 — 항상 빈칸 (변경 시에만 입력)
    usage_purpose: asset?.usage_purpose ?? '',
  }
}

interface AssetFormModalProps {
  open: boolean
  onClose: () => void
  /** 지정 시 수정 모드 */
  asset?: Asset | null
}

export function AssetFormModal({ open, onClose, asset }: AssetFormModalProps) {
  const { showToast } = useToast()
  const { data: clients = [] } = useClientOptions()
  const { options: assetGroupOptions } = useCodes('ASSET_GROUP')
  const { options: assetTypeOptions } = useCodes('ASSET_TYPE')
  const { options: assetStatusOptions } = useCodes('ASSET_STATUS')
  const save = useSaveAsset(asset?.asset_id)

  const [form, setForm] = useState<FormState>(() => initForm(asset))

  useEffect(() => {
    if (open) setForm(initForm(asset))
  }, [open, asset])

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!form.client_id) {
      showToast('고객사를 선택해 주세요.', 'danger')
      return
    }
    if (!form.quantity || Number(form.quantity) <= 0) {
      showToast('수량을 입력해 주세요.', 'danger')
      return
    }
    if (form.auth_type === 'ID_PW' && !form.login_id.trim()) {
      showToast('로그인 ID를 입력해 주세요.', 'danger')
      return
    }

    const payload: AssetPayload = {
      client_id: form.client_id,
      asset_group: form.asset_group,
      asset_type: form.asset_type || null,
      quantity: Number(form.quantity),
      main_spec: form.main_spec.trim() || null,
      telemetry_yn: form.telemetry_yn,
      location_info: form.location_info.trim() || null,
      status: form.status,
      agency_name: form.agency_name.trim() || null,
      site_url: form.site_url.trim() || null,
      auth_type: form.auth_type,
      login_id: form.auth_type === 'ID_PW' ? form.login_id.trim() || null : null,
      usage_purpose: form.usage_purpose.trim() || null,
    }
    // 인증 정보(auth_value)는 입력한 경우에만 전송 (미입력 = 기존 값 유지, 서버 AES-256-GCM 암호화)
    if (form.auth_secret && form.auth_type !== 'NONE') {
      payload.auth_value = form.auth_secret
    }

    try {
      await save.mutateAsync(payload)
      showToast(asset ? '자산 정보가 수정되었습니다.' : '자산이 등록되었습니다.', 'success')
      onClose()
    } catch {
      showToast('저장에 실패했습니다. 잠시 후 다시 시도해 주세요.', 'danger')
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={asset ? '자산 수정' : '신규 자산 등록'} size="lg">
      <form onSubmit={handleSubmit} className="max-h-[70vh] space-y-4 overflow-y-auto pr-1">
        {/* 자산 기본 */}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="고객사" required>
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
          <Field label="대분류" required>
            <select
              value={form.asset_group}
              onChange={(e) => set('asset_group', e.target.value)}
              className={inputCls}
            >
              {form.asset_group &&
                !assetGroupOptions.some((o) => o.value === form.asset_group) && (
                  <option value={form.asset_group}>{form.asset_group}</option>
                )}
              {assetGroupOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="소분류 (연료)" required>
            <select
              value={form.asset_type}
              onChange={(e) => set('asset_type', e.target.value)}
              className={inputCls}
            >
              {form.asset_type &&
                !assetTypeOptions.some((o) => o.value === form.asset_type) && (
                  <option value={form.asset_type}>{form.asset_type}</option>
                )}
              {assetTypeOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="수량" required>
            <input
              type="number"
              min={1}
              value={form.quantity}
              onChange={(e) => set('quantity', e.target.value)}
              className={inputCls}
              placeholder="예: 15"
            />
          </Field>
          <Field label="주요 제원">
            <input
              value={form.main_spec}
              onChange={(e) => set('main_spec', e.target.value)}
              className={inputCls}
              placeholder="예: 11톤 탑차 / 50kW"
            />
          </Field>
          <Field label="관제 연동 여부" required>
            <select
              value={form.telemetry_yn}
              onChange={(e) => set('telemetry_yn', e.target.value)}
              className={inputCls}
            >
              <option value="Y">연동 (Y)</option>
              <option value="N">미연동 (N)</option>
            </select>
          </Field>
          <Field label="위치·노선 정보">
            <input
              value={form.location_info}
              onChange={(e) => set('location_info', e.target.value)}
              className={inputCls}
              placeholder="예: 서울 강서 차고지"
            />
          </Field>
          <Field label="운영 상태" required>
            <select
              value={form.status}
              onChange={(e) => set('status', e.target.value)}
              className={inputCls}
            >
              {form.status &&
                !assetStatusOptions.some((o) => o.value === form.status) && (
                  <option value={form.status}>{form.status}</option>
                )}
              {assetStatusOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>
        </div>

        {/* 외부기관 연동 */}
        <div className="border-t border-hairline pt-3">
          <p className="mb-2 text-xs font-semibold tracking-wider text-slatey uppercase">
            외부기관 연동
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="대상 기관">
              <input
                value={form.agency_name}
                onChange={(e) => set('agency_name', e.target.value)}
                className={inputCls}
                placeholder="예: 한국환경공단, K-FMS"
              />
            </Field>
            <Field label="연동 목적">
              <input
                value={form.usage_purpose}
                onChange={(e) => set('usage_purpose', e.target.value)}
                className={inputCls}
                placeholder="예: 운행 기록 수집"
              />
            </Field>
            <div className="sm:col-span-2">
              <Field label="접속 URL">
                <input
                  type="url"
                  value={form.site_url}
                  onChange={(e) => set('site_url', e.target.value)}
                  className={inputCls}
                  placeholder="https://"
                />
              </Field>
            </div>
          </div>
        </div>

        {/* 보안 접속 정보 — 인증 방식에 따라 동적 표시 */}
        <div className="border-t border-hairline pt-3">
          <p className="mb-2 text-xs font-semibold tracking-wider text-slatey uppercase">
            보안 접속 정보
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="인증 방식">
              <select
                value={form.auth_type}
                onChange={(e) => set('auth_type', e.target.value)}
                className={inputCls}
              >
                <option value="NONE">없음 (NONE)</option>
                <option value="ID_PW">ID/PW</option>
                <option value="API_KEY">API 키</option>
              </select>
            </Field>
            {form.auth_type === 'ID_PW' && (
              <>
                <Field label="로그인 ID" required>
                  <input
                    value={form.login_id}
                    onChange={(e) => set('login_id', e.target.value)}
                    className={inputCls}
                  />
                </Field>
                <Field label="비밀번호">
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={form.auth_secret}
                    onChange={(e) => set('auth_secret', e.target.value)}
                    className={inputCls}
                    placeholder={asset ? '변경 시에만 입력' : ''}
                  />
                </Field>
              </>
            )}
            {form.auth_type === 'API_KEY' && (
              <div className="sm:col-span-2">
                <Field label="API 토큰">
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={form.auth_secret}
                    onChange={(e) => set('auth_secret', e.target.value)}
                    className={inputCls}
                    placeholder={asset ? '변경 시에만 입력' : ''}
                  />
                </Field>
              </div>
            )}
          </div>
          {form.auth_type !== 'NONE' && (
            <p className="mt-2 text-xs text-slatey">
              인증 정보는 서버에 암호화 저장되며, 저장 후에는 목록의 일시 표시(reveal)로만 확인할 수
              있습니다.
            </p>
          )}
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
            {asset ? '수정 저장' : '등록'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
