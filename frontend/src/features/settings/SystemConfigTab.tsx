// SCR-14 시스템 설정 탭 (ADMIN 전용) — tb_config 카드 목록
// sensitive_keywords: chips 편집 · funnel_mapping: 퍼널 4단계별 리텐션 다중 선택 · 그 외: JSON textarea
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  CaretDown,
  CaretUp,
  ClockCounterClockwise,
  Gear,
  Plus,
  X,
} from '@phosphor-icons/react'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCards } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { fmtDate, fmtDateTime, fmtTime } from '../../lib/format'
import {
  useConfigHistory,
  useConfigList,
  useSaveConfig,
  type ConfigItem,
} from './api'

// 리텐션 8단계 — 백엔드 funnel_mapping 기본값은 한국어 라벨을 사용(§10.2)
const RETENTION_STAGES = [
  { code: 'AWARENESS', label: '인지' },
  { code: 'INTEREST', label: '관심' },
  { code: 'REVIEW', label: '검토' },
  { code: 'DECISION', label: '구매결정' },
  { code: 'ONBOARDING', label: '온보딩' },
  { code: 'UTILIZATION', label: '활용' },
  { code: 'RENEWAL', label: '재계약' },
  { code: 'EXPANSION', label: '확장' },
]

const RETENTION_CODE_TO_LABEL: Record<string, string> = Object.fromEntries(
  RETENTION_STAGES.map((s) => [s.code, s.label]),
)

// §10.2 기본 매핑 — 파싱 실패 시 편집 시작점
const DEFAULT_FUNNEL_MAPPING: Record<string, string[]> = {
  '관심/접촉': ['인지', '관심'],
  '제안/검토': ['검토'],
  '계약 진행': ['구매결정'],
  '온보딩/활성': ['온보딩', '활용', '재계약', '확장'],
}

// 알려진 키 한국어 제목 (미등록 키는 키 그대로 노출)
const CONFIG_TITLES: Record<string, string> = {
  sensitive_keywords: '민감 키워드 (카카오 상담)',
  funnel_mapping: '리텐션 퍼널 매핑 (대시보드)',
}

const CONFIG_ORDER = ['sensitive_keywords', 'funnel_mapping']

export function SystemConfigTab() {
  const { data: items, isLoading, isError, refetch } = useConfigList()

  const sorted = useMemo(() => {
    if (!items) return []
    return [...items].sort((a, b) => {
      const ai = CONFIG_ORDER.indexOf(a.key)
      const bi = CONFIG_ORDER.indexOf(b.key)
      if (ai !== -1 || bi !== -1) {
        return (ai === -1 ? CONFIG_ORDER.length : ai) - (bi === -1 ? CONFIG_ORDER.length : bi)
      }
      return a.key.localeCompare(b.key)
    })
  }, [items])

  if (isLoading) return <SkeletonCards count={2} />

  if (isError) {
    return (
      <EmptyState
        icon={<Gear size={36} />}
        title="시스템 설정을 불러오지 못했습니다"
        description="설정 API(GET /config)가 아직 배포되지 않았거나 서버에 연결할 수 없습니다."
        action={
          <button
            type="button"
            onClick={() => refetch()}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
          >
            다시 시도
          </button>
        }
      />
    )
  }

  if (sorted.length === 0) {
    return (
      <EmptyState
        icon={<Gear size={36} />}
        title="등록된 설정이 없습니다"
        description="tb_config에 설정 항목이 아직 없습니다."
      />
    )
  }

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {sorted.map((item) => (
        <ConfigCard key={item.key} item={item} />
      ))}
    </div>
  )
}

// ── 설정 카드 ────────────────────────────────────────────────────────
function ConfigCard({ item }: { item: ConfigItem }) {
  const { showToast } = useToast()
  const save = useSaveConfig()
  const [draft, setDraft] = useState(item.value)
  const [draftValid, setDraftValid] = useState(true)
  const [historyOpen, setHistoryOpen] = useState(false)

  // 저장/재조회로 서버 값이 바뀌면 드래프트 리셋
  useEffect(() => {
    setDraft(item.value)
    setDraftValid(true)
  }, [item.value])

  const dirty = draft !== item.value

  const handleSave = async () => {
    if (!draftValid) {
      showToast('저장할 수 없습니다 — 값이 유효하지 않습니다 (JSON 형식·빈 목록 확인).', 'danger')
      return
    }
    try {
      await save.mutateAsync({ key: item.key, value: draft })
      showToast(`'${item.key}' 설정이 저장되었습니다.`, 'success')
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      showToast(detail ?? '설정 저장에 실패했습니다.', 'danger')
    }
  }

  let editor: ReactNode
  if (item.key === 'sensitive_keywords') {
    editor = (
      <KeywordChipsEditor
        value={draft}
        onChange={(next, valid) => {
          setDraft(next)
          setDraftValid(valid)
        }}
      />
    )
  } else if (item.key === 'funnel_mapping') {
    editor = (
      <FunnelMappingEditor
        value={draft}
        onChange={(next) => {
          setDraft(next)
          setDraftValid(true)
        }}
      />
    )
  } else {
    editor = (
      <JsonEditor
        value={draft}
        onChange={(next, valid) => {
          setDraft(next)
          setDraftValid(valid)
        }}
      />
    )
  }

  return (
    <div className="flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      {/* 헤더 */}
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-bold text-slate-900">
          {CONFIG_TITLES[item.key] ?? item.key}
        </h3>
        <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-500">
          {item.key}
        </code>
        {item.is_default && (
          <span className="inline-flex rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700">
            기본값 (미저장)
          </span>
        )}
      </div>
      {item.description && (
        <p className="mt-1 text-xs text-slate-400">{item.description}</p>
      )}
      {!item.is_default && item.updated_at && (
        <p className="mt-1 text-xs text-slate-400">
          최종 수정 {fmtDateTime(item.updated_at)}
          {item.updated_by_name ? ` · ${item.updated_by_name}` : ''}
        </p>
      )}

      {/* 편집기 */}
      <div className="mt-3 flex-1">{editor}</div>

      {/* 푸터: 이력 토글 + 저장 */}
      <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3">
        <button
          type="button"
          onClick={() => setHistoryOpen((v) => !v)}
          className="flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-700"
        >
          <ClockCounterClockwise size={14} />
          변경 이력
          {historyOpen ? <CaretUp size={12} /> : <CaretDown size={12} />}
        </button>
        <button
          type="button"
          disabled={!dirty || save.isPending}
          onClick={handleSave}
          className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {save.isPending ? '저장 중…' : '저장'}
        </button>
      </div>

      {historyOpen && <ConfigHistoryList configKey={item.key} />}
    </div>
  )
}

// ── 변경 이력 (접힘 해제 시 조회) ────────────────────────────────────
function ConfigHistoryList({ configKey }: { configKey: string }) {
  const { data: history, isLoading, isError } = useConfigHistory(configKey, true)

  if (isLoading) {
    return <p className="mt-3 text-xs text-slate-400">이력을 불러오는 중…</p>
  }
  if (isError) {
    return (
      <p className="mt-3 text-xs text-rose-500">
        이력을 불러오지 못했습니다 (GET /config/{configKey}/history)
      </p>
    )
  }
  if (!history || history.length === 0) {
    return <p className="mt-3 text-xs text-slate-400">변경 이력이 없습니다.</p>
  }

  return (
    <ul className="mt-3 max-h-48 space-y-2 overflow-y-auto rounded-lg bg-slate-50 p-3">
      {history.map((h, idx) => (
        <li
          key={h.history_id ?? idx}
          className="border-b border-slate-100 pb-2 text-xs last:border-b-0 last:pb-0"
        >
          <p className="text-slate-500">
            {h.created_at ? `${fmtDate(h.created_at)} ${fmtTime(h.created_at)}` : '—'}
            {h.updated_by_name ? ` · ${h.updated_by_name}` : ''}
          </p>
          <p className="mt-0.5 break-all font-mono text-[11px] text-slate-400">
            <span className="line-through">{truncate(h.old_value)}</span>
            <span className="mx-1 text-slate-300">→</span>
            <span className="text-slate-600">{truncate(h.new_value)}</span>
          </p>
        </li>
      ))}
    </ul>
  )
}

function truncate(value?: string | null, max = 120): string {
  if (!value) return '(없음)'
  return value.length > max ? `${value.slice(0, max)}…` : value
}

// ── sensitive_keywords: chips 편집 ──────────────────────────────────
function parseKeywords(value: string): string[] {
  try {
    const parsed = JSON.parse(value)
    if (Array.isArray(parsed)) return parsed.filter((v): v is string => typeof v === 'string')
  } catch {
    /* 파싱 실패 → 빈 목록에서 시작 */
  }
  return []
}

function KeywordChipsEditor({
  value,
  onChange,
}: {
  value: string
  /** 서버 검증(비어 있지 않은 문자열 배열)에 맞춰 빈 목록은 invalid */
  onChange: (serialized: string, valid: boolean) => void
}) {
  const keywords = useMemo(() => parseKeywords(value), [value])
  const [input, setInput] = useState('')

  const commit = (next: string[]) => onChange(JSON.stringify(next), next.length > 0)

  const add = () => {
    const kw = input.trim()
    if (!kw) return
    if (keywords.includes(kw)) {
      setInput('')
      return
    }
    commit([...keywords, kw])
    setInput('')
  }

  return (
    <div>
      <div className="flex flex-wrap gap-1.5">
        {keywords.length === 0 && (
          <p className="text-xs text-slate-400">등록된 키워드가 없습니다.</p>
        )}
        {keywords.map((kw) => (
          <span
            key={kw}
            className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700"
          >
            {kw}
            <button
              type="button"
              onClick={() => commit(keywords.filter((k) => k !== kw))}
              className="text-slate-400 hover:text-rose-500"
              aria-label={`${kw} 삭제`}
            >
              <X size={12} weight="bold" />
            </button>
          </span>
        ))}
      </div>
      <div className="mt-2.5 flex gap-1.5">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add()
            }
          }}
          placeholder="키워드 입력 후 Enter"
          className="h-9 flex-1 rounded-lg border border-slate-200 px-3 text-sm placeholder:text-slate-400 focus:border-slate-500 focus:outline-none"
        />
        <button
          type="button"
          onClick={add}
          disabled={!input.trim()}
          className="flex h-9 items-center gap-1 rounded-lg border border-slate-200 px-3 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40"
        >
          <Plus size={14} weight="bold" />
          추가
        </button>
      </div>
      <p className="mt-1.5 text-[11px] text-slate-400">
        카카오 상담 발화에 포함되면 자동으로 담당자 연결(민감 정보 응대 차단)됩니다.
      </p>
    </div>
  )
}

// ── funnel_mapping: 퍼널 4단계별 리텐션 다중 선택 ───────────────────
function parseFunnelMapping(value: string): Record<string, string[]> {
  try {
    const parsed = JSON.parse(value)
    if (
      parsed &&
      typeof parsed === 'object' &&
      !Array.isArray(parsed) &&
      Object.values(parsed).every((v) => Array.isArray(v))
    ) {
      // 영문 코드(AWARENESS 등)로 저장된 경우 한국어 라벨로 정규화
      const normalized: Record<string, string[]> = {}
      for (const [stage, list] of Object.entries(parsed as Record<string, unknown[]>)) {
        normalized[stage] = list
          .filter((v): v is string => typeof v === 'string')
          .map((v) => RETENTION_CODE_TO_LABEL[v] ?? v)
      }
      return normalized
    }
  } catch {
    /* 파싱 실패 → 기본 매핑에서 시작 */
  }
  return { ...DEFAULT_FUNNEL_MAPPING }
}

function FunnelMappingEditor({
  value,
  onChange,
}: {
  value: string
  onChange: (serialized: string) => void
}) {
  const mapping = useMemo(() => parseFunnelMapping(value), [value])
  const funnelStages = Object.keys(mapping)

  const toggle = (stage: string, label: string) => {
    const current = mapping[stage] ?? []
    const next = {
      ...mapping,
      [stage]: current.includes(label)
        ? current.filter((l) => l !== label)
        : [...current, label],
    }
    onChange(JSON.stringify(next))
  }

  // 검증 힌트: 중복 배정 / 미배정 리텐션 단계
  const assigned = Object.values(mapping).flat()
  const duplicated = RETENTION_STAGES.filter(
    (s) => assigned.filter((a) => a === s.label).length > 1,
  ).map((s) => s.label)
  const unassigned = RETENTION_STAGES.filter((s) => !assigned.includes(s.label)).map(
    (s) => s.label,
  )

  return (
    <div className="space-y-3">
      {funnelStages.map((stage) => (
        <div key={stage}>
          <p className="mb-1.5 text-xs font-semibold text-slate-600">{stage}</p>
          <div className="flex flex-wrap gap-1.5">
            {RETENTION_STAGES.map((s) => {
              const selected = (mapping[stage] ?? []).includes(s.label)
              return (
                <button
                  key={s.code}
                  type="button"
                  onClick={() => toggle(stage, s.label)}
                  aria-pressed={selected}
                  className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                    selected
                      ? 'border-emerald-300 bg-emerald-50 text-emerald-700'
                      : 'border-slate-200 bg-white text-slate-400 hover:border-slate-300 hover:text-slate-600'
                  }`}
                >
                  {s.label}
                </button>
              )
            })}
          </div>
        </div>
      ))}
      {(duplicated.length > 0 || unassigned.length > 0) && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-[11px] text-amber-700">
          {duplicated.length > 0 && `중복 배정: ${duplicated.join(', ')}`}
          {duplicated.length > 0 && unassigned.length > 0 && ' · '}
          {unassigned.length > 0 && `미배정: ${unassigned.join(', ')}`}
        </p>
      )}
    </div>
  )
}

// ── 기타 키: JSON textarea ───────────────────────────────────────────
function JsonEditor({
  value,
  onChange,
}: {
  value: string
  onChange: (next: string, valid: boolean) => void
}) {
  const valid = useMemo(() => {
    if (!value.trim()) return false
    try {
      JSON.parse(value)
      return true
    } catch {
      return false
    }
  }, [value])

  return (
    <div>
      <textarea
        value={value}
        onChange={(e) => {
          const next = e.target.value
          let ok = false
          try {
            JSON.parse(next)
            ok = next.trim().length > 0
          } catch {
            ok = false
          }
          onChange(next, ok)
        }}
        rows={5}
        spellCheck={false}
        className={`w-full rounded-lg border p-3 font-mono text-xs text-slate-700 focus:outline-none ${
          valid ? 'border-slate-200 focus:border-slate-500' : 'border-rose-300 focus:border-rose-400'
        }`}
      />
      {!valid && (
        <p className="mt-1 text-[11px] text-rose-500">유효한 JSON 형식이 아닙니다.</p>
      )}
    </div>
  )
}
