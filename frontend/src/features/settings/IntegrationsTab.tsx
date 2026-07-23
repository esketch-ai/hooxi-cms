// SCR-14 연동 관리 탭 (ADMIN 전용) — 외부 연동 자격증명 입력·저장·연결 테스트
// Dropbox: OAuth 승인 마법사 3스텝 · 카카오 챗봇: 웹훅 URL 복사 + 시크릿 자동 생성
import { useEffect, useMemo, useState } from 'react'
import {
  ArrowSquareOut,
  CheckCircle,
  CircleNotch,
  Copy,
  LinkSimple,
  PlugsConnected,
  Sparkle,
  Trash,
  XCircle,
} from '@phosphor-icons/react'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCards } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import {
  useDropboxAuthorizeUrl,
  useDropboxExchange,
  useIntegrations,
  useKakaoWebhookUrl,
  useSaveIntegration,
  useTestIntegration,
  type Integration,
  type IntegrationField,
  type IntegrationTestResult,
} from './api'

// 카드 표시 순서 (미등록 연동은 뒤에 이름순) — backend/services/integration_config.py REGISTRY 기준
const INTEGRATION_ORDER = ['dropbox', 'solapi', 'kakao_bot', 'gmail', 'naver_works']

// 각 연동별 도움말 1줄 + 발급처 링크
const HELP_LINKS: Record<string, { text: string; href: string; linkLabel: string }> = {
  dropbox: {
    text: 'Dropbox App Console에서 앱을 만들고 App Key·App Secret을 발급받으세요.',
    href: 'https://www.dropbox.com/developers/apps',
    linkLabel: 'Dropbox App Console',
  },
  solapi: {
    text: 'SOLAPI 콘솔에서 API 키·시크릿을 발급받고 카카오 채널(발신프로필 PF ID)을 연동하세요.',
    href: 'https://console.solapi.com',
    linkLabel: 'SOLAPI 콘솔',
  },
  kakao_bot: {
    text: '카카오 오픈빌더에서 봇 ID·이벤트 API 키를 확인하세요.',
    href: 'https://chatbot.kakao.com',
    linkLabel: '카카오 오픈빌더',
  },
  gmail: {
    text: 'Google 계정 2단계 인증 활성화 후 앱 비밀번호를 생성해 입력하세요.',
    href: 'https://myaccount.google.com/apppasswords',
    linkLabel: 'Google 앱 비밀번호',
  },
  naver_works: {
    text: '네이버웍스 개발자 콘솔에서 앱을 등록하고 인증 정보를 발급받으세요.',
    href: 'https://dev.worksmobile.com',
    linkLabel: '네이버웍스 개발자 콘솔',
  },
}

function helpFor(name: string) {
  if (HELP_LINKS[name]) return HELP_LINKS[name]
  const found = Object.keys(HELP_LINKS).find((k) => name.includes(k) || k.includes(name))
  return found ? HELP_LINKS[found] : null
}

/** 랜덤 hex 32자 (16바이트) — KAKAO_WEBHOOK_SECRET 자동 생성용 */
function randomHex32(): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

// ── 탭 루트 ──────────────────────────────────────────────────────────
export function IntegrationsTab() {
  const { data: integrations, isLoading, isError, refetch } = useIntegrations()

  const sorted = useMemo(() => {
    if (!integrations) return []
    return [...integrations].sort((a, b) => {
      const ai = INTEGRATION_ORDER.indexOf(a.name)
      const bi = INTEGRATION_ORDER.indexOf(b.name)
      if (ai !== -1 || bi !== -1) {
        return (
          (ai === -1 ? INTEGRATION_ORDER.length : ai) -
          (bi === -1 ? INTEGRATION_ORDER.length : bi)
        )
      }
      return a.name.localeCompare(b.name)
    })
  }, [integrations])

  if (isLoading) return <SkeletonCards count={4} />

  if (isError) {
    return (
      <EmptyState
        icon={<PlugsConnected size={36} />}
        title="연동 정보를 불러오지 못했습니다"
        description="연동 설정을 불러오지 못했습니다. 잠시 후 다시 시도하거나 관리자에게 문의하세요."
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

  if (sorted.length === 0) {
    return (
      <EmptyState
        icon={<PlugsConnected size={36} />}
        title="등록된 연동이 없습니다"
        description="서버에 설정 가능한 외부 연동이 없습니다."
      />
    )
  }

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {sorted.map((integration) => (
        <IntegrationCard key={integration.name} integration={integration} />
      ))}
    </div>
  )
}

// ── 상태 뱃지 ────────────────────────────────────────────────────────
// 뱃지는 "값이 저장됐는지"만 나타낸다 — 실제 연결 성공은 '연결 테스트'로 확인한다.
// (예: Gmail 앱 비밀번호를 틀리게 저장해도 값은 채워지므로, 초록 '연동됨'은 오해를 준다)
function statusOf(fields: IntegrationField[]): { label: string; cls: string; hint: string } {
  const required = fields.filter((f) => f.required)
  const target = required.length > 0 ? required : fields
  const configured = fields.filter((f) => f.configured)
  if (target.length > 0 && target.every((f) => f.configured)) {
    return {
      label: '설정됨',
      cls: 'bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-400/25',
      hint: '필수 값이 모두 저장됨 — 실제 연결 여부는 아래 [연결 테스트]로 확인하세요.',
    }
  }
  if (configured.length > 0) {
    return {
      label: '부분 설정',
      cls: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-400/25',
      hint: '일부 값만 저장됨 — 필수 값을 모두 채워야 연동이 동작합니다.',
    }
  }
  return { label: '미설정', cls: 'bg-elevate-strong text-ash border-hairline', hint: '저장된 값이 없습니다.' }
}

// ── 연동 카드 ────────────────────────────────────────────────────────
function IntegrationCard({ integration }: { integration: Integration }) {
  const { showToast } = useToast()
  const save = useSaveIntegration()
  const test = useTestIntegration()

  // 필드 드래프트: 입력값(빈 문자열=미변경) + 삭제 표시
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [deletes, setDeletes] = useState<Set<string>>(new Set())
  const [testResult, setTestResult] = useState<IntegrationTestResult | null>(null)

  // 저장/재조회로 서버 값이 갱신되면 드래프트 리셋
  useEffect(() => {
    setDrafts({})
    setDeletes(new Set())
  }, [integration])

  const status = statusOf(integration.fields)
  const help = helpFor(integration.name)

  const dirty =
    deletes.size > 0 || Object.values(drafts).some((v) => v.trim().length > 0)

  const buildPayload = (): Record<string, string | null> => {
    const values: Record<string, string | null> = {}
    for (const [key, value] of Object.entries(drafts)) {
      if (deletes.has(key)) continue
      if (value.trim()) values[key] = value.trim()
    }
    for (const key of deletes) values[key] = null
    return values
  }

  const handleSave = async () => {
    const values = buildPayload()
    if (Object.keys(values).length === 0) {
      showToast('변경된 값이 없습니다.', 'info')
      return
    }
    try {
      await save.mutateAsync({ name: integration.name, values })
      showToast(`${integration.label} 설정이 저장되었습니다.`, 'success')
      setTestResult(null)
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      showToast(detail ?? '연동 설정 저장에 실패했습니다.', 'danger')
    }
  }

  const runTest = async () => {
    setTestResult(null)
    try {
      const result = await test.mutateAsync(integration.name)
      setTestResult(result)
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      setTestResult({ ok: false, message: detail ?? '연결 테스트 요청에 실패했습니다.' })
    }
  }

  const setDraft = (key: string, value: string) =>
    setDrafts((prev) => ({ ...prev, [key]: value }))

  const toggleDelete = (key: string) =>
    setDeletes((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  return (
    <div className="flex flex-col rounded-3xl border border-hairline bg-graphite p-5">
      {/* 헤더: 이름 + 상태 뱃지 */}
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-bold text-bone">{integration.label}</h3>
        <code className="rounded bg-elevate-strong px-1.5 py-0.5 font-mono text-[11px] text-ash">
          {integration.name}
        </code>
        <span
          className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${status.cls}`}
          title={status.hint}
        >
          {status.label}
        </span>
      </div>
      {integration.description && (
        <p className="mt-1 text-xs text-slatey">{integration.description}</p>
      )}

      {/* 카카오 챗봇: 웹훅 URL 안내 */}
      {integration.name === 'kakao_bot' && <KakaoWebhookUrlBox />}

      {/* 필드 입력 */}
      <div className="mt-3 flex-1 space-y-3">
        {integration.fields.map((field) => (
          <FieldRow
            key={field.key}
            field={field}
            draft={drafts[field.key] ?? ''}
            markedDelete={deletes.has(field.key)}
            onChange={(v) => setDraft(field.key, v)}
            onToggleDelete={() => toggleDelete(field.key)}
            extraAction={
              integration.name === 'kakao_bot' &&
              field.key === 'KAKAO_WEBHOOK_SECRET' &&
              !field.configured ? (
                <button
                  type="button"
                  onClick={() => {
                    setDraft(field.key, randomHex32())
                    showToast('시크릿이 생성되었습니다. [저장]을 눌러 적용하세요.', 'info')
                  }}
                  className="flex items-center gap-1 rounded-lg border border-hairline px-2 py-1 text-[11px] font-medium text-bone hover:bg-elevate"
                >
                  <Sparkle size={12} />
                  시크릿 자동 생성
                </button>
              ) : null
            }
          />
        ))}
        {integration.fields.length === 0 && (
          <p className="text-xs text-slatey">설정할 필드가 없습니다.</p>
        )}
      </div>

      {/* Dropbox: OAuth 승인 마법사 */}
      {integration.name === 'dropbox' && (
        <DropboxOAuthWizard
          integration={integration}
          onConnected={runTest}
        />
      )}

      {/* 연결 테스트 결과 */}
      {testResult && (
        <div
          className={`mt-3 flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm ${
            testResult.ok
              ? 'border-emerald-400/25 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
              : 'border-rose-400/25 bg-rose-500/15 text-rose-700 dark:text-rose-300'
          }`}
        >
          {testResult.ok ? (
            <CheckCircle size={16} className="mt-0.5 shrink-0" />
          ) : (
            <XCircle size={16} className="mt-0.5 shrink-0" />
          )}
          <span className="break-all">
            {testResult.message || (testResult.ok ? '연결에 성공했습니다.' : '연결에 실패했습니다.')}
          </span>
        </div>
      )}

      {/* 푸터: 도움말 + 저장·테스트 */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-hairline pt-3">
        {help ? (
          <p className="min-w-0 flex-1 text-[11px] leading-relaxed text-slatey">
            {help.text}{' '}
            <a
              href={help.href}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-0.5 font-medium text-ash underline hover:text-bone"
            >
              {help.linkLabel}
              <ArrowSquareOut size={11} />
            </a>
          </p>
        ) : (
          <span />
        )}
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={runTest}
            disabled={test.isPending}
            className="flex items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate disabled:opacity-50"
          >
            {test.isPending ? (
              <CircleNotch size={14} className="animate-spin" />
            ) : (
              <PlugsConnected size={14} />
            )}
            연결 테스트
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={!dirty || save.isPending}
            className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {save.isPending ? '저장 중…' : '저장'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── 필드 1행 ─────────────────────────────────────────────────────────
function FieldRow({
  field,
  draft,
  markedDelete,
  onChange,
  onToggleDelete,
  extraAction,
}: {
  field: IntegrationField
  draft: string
  markedDelete: boolean
  onChange: (value: string) => void
  onToggleDelete: () => void
  extraAction?: React.ReactNode
}) {
  const placeholder = field.secret
    ? field.configured
      ? '설정됨 — 변경하려면 새 값 입력'
      : '값 입력'
    : field.configured
      ? '설정됨 — 변경하려면 새 값 입력'
      : '값 입력'

  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center gap-1.5">
        <label className="text-xs font-medium text-ash">{field.label}</label>
        <code className="rounded bg-elevate-strong px-1 py-0.5 font-mono text-[10px] text-slatey">
          {field.key}
        </code>
        {field.required && (
          <span className="text-[10px] font-medium text-rose-400">필수</span>
        )}
        {field.source === 'env' && (
          <span
            className="inline-flex rounded-full border border-sky-400/25 bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-medium text-sky-700 dark:text-sky-300"
            title="DB에 저장된 값이 없어 서버 환경변수 값을 사용 중입니다"
          >
            환경변수
          </span>
        )}
        <span className="ml-auto flex items-center gap-1.5">
          {extraAction}
          {field.configured && field.source !== 'env' && (
            <button
              type="button"
              onClick={onToggleDelete}
              title={markedDelete ? '삭제 취소' : '저장된 값 삭제'}
              className={`flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] font-medium ${
                markedDelete
                  ? 'border-rose-400/40 bg-rose-500/15 text-rose-700 dark:text-rose-300'
                  : 'border-hairline text-ash hover:bg-rose-500/10 hover:text-rose-700 dark:text-rose-300'
              }`}
            >
              <Trash size={12} />
              {markedDelete ? '삭제 예정 — 취소' : '삭제'}
            </button>
          )}
        </span>
      </div>
      <input
        type={field.secret ? 'password' : 'text'}
        value={draft}
        onChange={(e) => onChange(e.target.value)}
        disabled={markedDelete}
        placeholder={markedDelete ? '저장 시 이 값이 삭제됩니다' : placeholder}
        autoComplete="off"
        className={`h-9 w-full rounded-lg border bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:outline-none disabled:bg-rose-500/10 disabled:placeholder:text-rose-400 ${
          markedDelete
            ? 'border-rose-400/25'
            : 'border-hairline focus:border-white/30'
        }`}
      />
      {field.secret && field.configured && !markedDelete && (
        <p className="mt-0.5 text-[10px] text-slatey">
          보안을 위해 저장된 값은 표시되지 않습니다. 빈 채로 저장하면 기존 값이 유지됩니다.
        </p>
      )}
    </div>
  )
}

// ── 카카오 챗봇: 웹훅 URL 표시 + 복사 ────────────────────────────────
function KakaoWebhookUrlBox() {
  const { showToast } = useToast()
  const { data, isError } = useKakaoWebhookUrl(true)

  if (isError || !data?.url) return null

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(data.url)
      showToast('웹훅 URL이 복사되었습니다.', 'success')
    } catch {
      showToast('복사에 실패했습니다. URL을 직접 선택해 복사하세요.', 'danger')
    }
  }

  return (
    <div className="mt-3 rounded-lg border border-hairline bg-graphite-2 p-3">
      <p className="text-[11px] font-medium text-ash">
        스킬 서버 웹훅 URL — 카카오 오픈빌더 폴백 블록에 등록하세요
      </p>
      <div className="mt-1.5 flex items-center gap-1.5">
        <code className="min-w-0 flex-1 truncate rounded bg-void px-2 py-1.5 font-mono text-[11px] text-ash ring-1 ring-hairline">
          {data.url}
        </code>
        <button
          type="button"
          onClick={copy}
          title="복사"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-hairline bg-graphite text-ash hover:bg-elevate hover:text-bone"
        >
          <Copy size={14} />
        </button>
      </div>
    </div>
  )
}

// ── Dropbox OAuth 승인 마법사 ────────────────────────────────────────
function DropboxOAuthWizard({
  integration,
  onConnected,
}: {
  integration: Integration
  onConnected: () => void
}) {
  const { showToast } = useToast()
  const authorizeUrl = useDropboxAuthorizeUrl()
  const exchange = useDropboxExchange()
  const [code, setCode] = useState('')
  const [exchangeError, setExchangeError] = useState<string | null>(null)

  const appKeyReady = integration.fields
    .filter((f) => f.key === 'DROPBOX_APP_KEY' || f.key === 'DROPBOX_APP_SECRET')
    .every((f) => f.configured)
  const refreshTokenField = integration.fields.find((f) => f.key === 'DROPBOX_REFRESH_TOKEN')
  const connected = !!refreshTokenField?.configured

  const openAuthorize = async () => {
    try {
      const { url } = await authorizeUrl.mutateAsync()
      window.open(url, '_blank', 'noopener')
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      showToast(detail ?? '승인 URL 생성에 실패했습니다. App Key·Secret 저장 여부를 확인하세요.', 'danger')
    }
  }

  const runExchange = async () => {
    setExchangeError(null)
    try {
      const result = await exchange.mutateAsync(code.trim())
      if (result.ok === false) {
        setExchangeError(result.message || '코드 교환에 실패했습니다.')
        return
      }
      setCode('')
      showToast('Dropbox 연동이 완료되었습니다. 연결 테스트를 실행합니다.', 'success')
      onConnected()
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      setExchangeError(detail ?? '코드 교환에 실패했습니다. 코드를 다시 확인하세요.')
    }
  }

  return (
    <div className="mt-4 rounded-lg border border-hairline bg-graphite-2 p-3.5">
      <p className="flex items-center gap-1.5 text-xs font-semibold text-bone">
        <LinkSimple size={14} />
        OAuth 승인 마법사
        {connected && (
          <span className="inline-flex rounded-full border border-emerald-400/25 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:text-emerald-300">
            승인 완료
          </span>
        )}
      </p>

      <ol className="mt-2.5 space-y-2.5">
        <li className="flex gap-2 text-xs text-ash">
          <StepBullet n={1} done={appKeyReady} />
          <span className="pt-0.5">
            위 App Key·App Secret을 입력하고 <b>[저장]</b>하세요.
          </span>
        </li>
        <li className="flex gap-2 text-xs text-ash">
          <StepBullet n={2} done={connected} />
          <span className="min-w-0 flex-1 pt-0.5">
            <button
              type="button"
              onClick={openAuthorize}
              disabled={!appKeyReady || authorizeUrl.isPending}
              className="inline-flex items-center gap-1 rounded-lg border border-hairline bg-graphite px-2.5 py-1.5 text-xs font-medium text-bone hover:bg-elevate disabled:opacity-40"
            >
              {authorizeUrl.isPending ? (
                <CircleNotch size={12} className="animate-spin" />
              ) : (
                <ArrowSquareOut size={12} />
              )}
              승인 URL 열기
            </button>
            <span className="mt-1 block text-[11px] text-slatey">
              회사 Dropbox 계정으로 로그인된 브라우저에서 허용 후 표시되는 코드를 붙여넣으세요.
            </span>
          </span>
        </li>
        <li className="flex gap-2 text-xs text-ash">
          <StepBullet n={3} done={connected} />
          <span className="min-w-0 flex-1 pt-0.5">
            <span className="flex gap-1.5">
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="승인 코드 붙여넣기"
                autoComplete="off"
                spellCheck={false}
                className="h-8 min-w-0 flex-1 rounded-lg border border-hairline bg-graphite px-2.5 font-mono text-xs text-bone placeholder:font-sans placeholder:text-slatey focus:border-white/30 focus:outline-none"
              />
              <button
                type="button"
                onClick={runExchange}
                disabled={!code.trim() || exchange.isPending}
                className="flex h-8 shrink-0 items-center gap-1 rounded-full bg-primary px-3 text-xs font-medium text-on-primary hover:opacity-90 disabled:opacity-40"
              >
                {exchange.isPending && <CircleNotch size={12} className="animate-spin" />}
                연동 완료
              </button>
            </span>
            {exchangeError && (
              <span className="mt-1 block text-[11px] text-rose-500">{exchangeError}</span>
            )}
          </span>
        </li>
      </ol>
    </div>
  )
}

function StepBullet({ n, done }: { n: number; done: boolean }) {
  return (
    <span
      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
        done ? 'bg-emerald-500 text-white' : 'bg-elevate-strong text-ash'
      }`}
    >
      {done ? '✓' : n}
    </span>
  )
}
