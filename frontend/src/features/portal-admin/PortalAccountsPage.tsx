// INC-8b 외부 포털 계정 관리 — MANAGER↑ 전용
// 운수사(PARTNER)·투자금융사(INVESTOR) 포털 계정 발급·재발급·비활성 + 매직링크 복사
import { useMemo, useState } from 'react'
import {
  ArrowsClockwise,
  Copy,
  IdentificationCard,
  LinkSimple,
  Plus,
  Prohibit,
  ShieldCheck,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { DataTable, type Column } from '../../components/DataTable'
import { EmptyState } from '../../components/EmptyState'
import { Modal } from '../../components/Modal'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import { useClientOptions } from '../../lib/api/queries'
import { useBuyerOptions } from '../buyers/api'
import {
  absoluteMagicLink,
  useCreateExternalAccount,
  useDeactivateExternalAccount,
  useExternalAccounts,
  useResendMagicLink,
  type ExternalAccount,
  type ExternalAccountIn,
  type ExternalRole,
} from './api'

const ROLE_BADGES: Record<ExternalRole, { label: string; cls: string }> = {
  PARTNER: {
    label: '운수사',
    cls: 'bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-400/25',
  },
  INVESTOR: {
    label: '투자·금융사',
    cls: 'bg-violet-500/15 text-violet-700 dark:text-violet-300 border-violet-400/25',
  },
}

const STATUS_BADGES: Record<string, { label: string; cls: string }> = {
  PENDING: {
    label: '발급됨',
    cls: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-400/25',
  },
  ACTIVE: {
    label: '활성',
    cls: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-400/25',
  },
  INACTIVE: { label: '비활성', cls: 'bg-elevate-strong text-ash border-hairline' },
}

// 매직링크 발송 결과(delivery) → 화면 표시 문구·톤 (이메일 주채널 + 카카오 폴백)
const DELIVERY_BADGES: Record<string, { label: string; cls: string }> = {
  EMAIL_SENT: {
    label: '이메일로 발송됨',
    cls: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-400/25',
  },
  KAKAO_SENT: {
    label: '카카오 알림톡 발송됨',
    cls: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-400/25',
  },
  EMAIL_FAILED: {
    label: '이메일 발송 실패 — 아래 링크를 직접 전달하세요',
    cls: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-400/25',
  },
  KAKAO_FAILED: {
    label: '카카오 발송 실패 — 아래 링크를 직접 전달하세요',
    cls: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-400/25',
  },
  NOT_CONFIGURED: {
    label: '자동발송 미설정 — 아래 링크를 직접 전달하세요',
    cls: 'bg-elevate-strong text-ash border-hairline',
  },
}

const inputCls =
  'h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none'

interface IssueForm {
  role: ExternalRole
  email: string
  name: string
  phone: string
  client_id: string
  buyer_id: string
}

const EMPTY_FORM: IssueForm = {
  role: 'PARTNER',
  email: '',
  name: '',
  phone: '',
  client_id: '',
  buyer_id: '',
}

export function PortalAccountsPage() {
  const { user: me } = useAuth()
  const canManage = me?.role === 'ADMIN' || me?.role === 'MANAGER'

  const { showToast } = useToast()
  const { data: clients = [] } = useClientOptions()
  const { data: buyers = [] } = useBuyerOptions()

  const { data: accounts = [], isLoading, isError, refetch } = useExternalAccounts({ enabled: canManage })
  const createAccount = useCreateExternalAccount()
  const resendLink = useResendMagicLink()
  const deactivate = useDeactivateExternalAccount()

  const [issueOpen, setIssueOpen] = useState(false)
  const [form, setForm] = useState<IssueForm>(EMPTY_FORM)
  const [linkResult, setLinkResult] = useState<ExternalAccount | null>(null)
  const [deactivateTarget, setDeactivateTarget] = useState<ExternalAccount | null>(null)

  // 소속 표시용 id→이름 매핑
  const clientNameOf = useMemo(() => {
    const m: Record<string, string> = {}
    for (const c of clients) m[c.client_id] = c.company_name
    return m
  }, [clients])
  const buyerNameOf = useMemo(() => {
    const m: Record<string, string> = {}
    for (const b of buyers) m[b.buyer_id] = b.name
    return m
  }, [buyers])

  // PARTNER 발급은 운수사(TRANSPORT)만 선택 가능
  const transportClients = useMemo(
    () => clients.filter((c) => c.client_type === 'TRANSPORT'),
    [clients],
  )

  const run = async (fn: () => Promise<unknown>, successMsg: string, cleanup: () => void) => {
    try {
      await fn()
      showToast(successMsg, 'success')
      cleanup()
    } catch (error) {
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '처리에 실패했습니다.', 'danger')
    }
  }

  const copyLink = async (link?: string | null) => {
    const url = absoluteMagicLink(link)
    if (!url) return
    try {
      await navigator.clipboard.writeText(url)
      showToast('매직링크를 복사했습니다.', 'success')
    } catch {
      showToast('복사에 실패했습니다. 링크를 직접 선택해 복사해 주세요.', 'danger')
    }
  }

  const submitIssue = () => {
    const payload: ExternalAccountIn = {
      email: form.email.trim(),
      name: form.name.trim() || null,
      role: form.role,
      client_id: form.role === 'PARTNER' ? form.client_id || null : null,
      buyer_id: form.role === 'INVESTOR' ? form.buyer_id || null : null,
      phone: form.phone.trim() || undefined,
    }
    run(
      async () => {
        const created = await createAccount.mutateAsync(payload)
        setLinkResult(created)
      },
      '포털 계정이 발급되었습니다.',
      () => setIssueOpen(false),
    )
  }

  const canSubmit =
    !!form.email.trim() &&
    (form.role === 'PARTNER' ? !!form.client_id : !!form.buyer_id) &&
    !createAccount.isPending

  if (!canManage) {
    return (
      <div className="animate-fade-in space-y-4">
        <PageHeader title="외부 포털 계정" subtitle="운수사·투자금융사 포털 계정 관리" />
        <EmptyState
          icon={<ShieldCheck size={36} />}
          title="접근 권한이 없습니다"
          description="외부 포털 계정 관리는 팀장(MANAGER)·관리자(ADMIN)만 조회·변경할 수 있습니다."
        />
      </div>
    )
  }

  const columns: Column<ExternalAccount>[] = [
    {
      key: 'account',
      header: '계정',
      render: (a) => (
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-bone">{a.name ?? '—'}</p>
          <p className="truncate text-xs text-slatey">{a.email}</p>
        </div>
      ),
    },
    {
      key: 'role',
      header: '역할',
      render: (a) => {
        const spec = ROLE_BADGES[a.role]
        return (
          <span
            className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${spec.cls}`}
          >
            {spec.label}
          </span>
        )
      },
    },
    {
      key: 'belong',
      header: '소속',
      render: (a) => (
        <span className="text-sm text-ash">
          {a.role === 'PARTNER'
            ? a.client_id
              ? clientNameOf[a.client_id] ?? a.client_id
              : '—'
            : a.buyer_id
              ? buyerNameOf[a.buyer_id] ?? a.buyer_id
              : '—'}
        </span>
      ),
    },
    {
      key: 'status',
      header: '상태',
      render: (a) => {
        const spec = STATUS_BADGES[a.status] ?? STATUS_BADGES.INACTIVE
        return (
          <span
            className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${spec.cls}`}
          >
            {spec.label}
          </span>
        )
      },
    },
    {
      key: 'actions',
      header: '관리',
      className: 'text-right',
      render: (a) => (
        <div className="flex justify-end gap-1">
          {a.status !== 'INACTIVE' && (
            <>
              <button
                type="button"
                onClick={() =>
                  run(
                    async () => {
                      const res = await resendLink.mutateAsync(a.user_id)
                      setLinkResult(res)
                    },
                    '매직링크를 재발급했습니다.',
                    () => undefined,
                  )
                }
                className="flex items-center gap-1 rounded-full border border-hairline px-2.5 py-1.5 text-xs font-medium text-bone hover:bg-elevate"
                title="매직링크 재발급"
              >
                <ArrowsClockwise size={13} />
                재발급
              </button>
              <button
                type="button"
                onClick={() => setDeactivateTarget(a)}
                className="rounded-lg p-1.5 text-smoke hover:bg-rose-500/10 hover:text-rose-700 dark:hover:text-rose-300"
                title="비활성화"
                aria-label={`${a.email} 비활성화`}
              >
                <Prohibit size={15} />
              </button>
            </>
          )}
        </div>
      ),
    },
  ]

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="외부 포털 계정"
        subtitle="운수사·투자금융사 포털 계정 발급·재발급 (MANAGER 전용)"
        actions={
          <button
            type="button"
            onClick={() => {
              setForm(EMPTY_FORM)
              setIssueOpen(true)
            }}
            className="flex items-center gap-1.5 rounded-full bg-primary px-3.5 py-2 text-sm font-medium text-on-primary hover:opacity-90"
          >
            <Plus size={16} weight="bold" />
            포털 계정 발급
          </button>
        }
      />

      {isError ? (
        <EmptyState
          icon={<IdentificationCard size={36} />}
          title="목록을 불러오지 못했습니다"
          description="네트워크 상태를 확인한 뒤 다시 시도해 주세요."
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
      ) : (
        <DataTable
          columns={columns}
          rows={accounts}
          rowKey={(a) => a.user_id}
          isLoading={isLoading}
          emptyTitle="발급된 포털 계정이 없습니다"
          emptyDescription="우측 상단 [포털 계정 발급]으로 운수사·투자금융사 담당자 계정을 발급할 수 있습니다."
          rowClassName={(a) => (a.status === 'INACTIVE' ? 'opacity-50' : '')}
        />
      )}

      {/* 발급 폼 */}
      <Modal
        open={issueOpen}
        onClose={() => setIssueOpen(false)}
        title="포털 계정 발급"
        footer={
          <>
            <button
              type="button"
              onClick={() => setIssueOpen(false)}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
            >
              취소
            </button>
            <button
              type="button"
              disabled={!canSubmit}
              onClick={submitIssue}
              className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
            >
              발급
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-ash">역할</label>
            <div className="flex gap-2">
              {(['PARTNER', 'INVESTOR'] as ExternalRole[]).map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setForm((f) => ({ ...f, role: r, client_id: '', buyer_id: '' }))}
                  className={`flex-1 rounded-lg border px-3 py-2 text-sm font-medium ${
                    form.role === r
                      ? 'border-transparent bg-primary text-on-primary'
                      : 'border-hairline text-bone hover:bg-elevate'
                  }`}
                >
                  {ROLE_BADGES[r].label} ({r})
                </button>
              ))}
            </div>
          </div>

          {form.role === 'PARTNER' ? (
            <div>
              <label className="mb-1 block text-xs font-medium text-ash">
                운수사<span className="ml-0.5 text-rose-500">*</span>
              </label>
              <select
                value={form.client_id}
                onChange={(e) => setForm((f) => ({ ...f, client_id: e.target.value }))}
                className={inputCls}
              >
                <option value="">운수사 선택</option>
                {transportClients.map((c) => (
                  <option key={c.client_id} value={c.client_id}>
                    {c.company_name}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <label className="mb-1 block text-xs font-medium text-ash">
                매수자<span className="ml-0.5 text-rose-500">*</span>
              </label>
              <select
                value={form.buyer_id}
                onChange={(e) => setForm((f) => ({ ...f, buyer_id: e.target.value }))}
                className={inputCls}
              >
                <option value="">매수자 선택</option>
                {buyers.map((b) => (
                  <option key={b.buyer_id} value={b.buyer_id}>
                    {b.name}
                  </option>
                ))}
              </select>
              {buyers.length === 0 && (
                <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                  등록된 매수자가 없습니다. [매수자 마스터]에서 먼저 등록해 주세요.
                </p>
              )}
            </div>
          )}

          <div>
            <label className="mb-1 block text-xs font-medium text-ash">
              이메일<span className="ml-0.5 text-rose-500">*</span>
            </label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              placeholder="name@example.com"
              className={inputCls}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ash">이름</label>
            <input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className={inputCls}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ash">전화번호</label>
            <input
              type="tel"
              value={form.phone}
              onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
              placeholder="010-0000-0000"
              className={inputCls}
            />
            <p className="mt-1 text-xs text-slatey">
              입력 시 카카오 알림톡으로 매직링크가 자동 발송됩니다. (선택)
            </p>
          </div>
        </div>
      </Modal>

      {/* 매직링크 결과 (발급·재발급 공통) */}
      <Modal
        open={!!linkResult}
        onClose={() => setLinkResult(null)}
        title="매직링크"
        footer={
          <button
            type="button"
            onClick={() => setLinkResult(null)}
            className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90"
          >
            닫기
          </button>
        }
      >
        {linkResult && (
          <div className="space-y-3">
            <p className="text-sm text-ash">
              <b className="text-bone">{linkResult.name ?? linkResult.email}</b> 님의 포털 로그인
              링크입니다. 아래 링크를 복사해 담당자에게 전달해 주세요.
            </p>
            {linkResult.delivery && DELIVERY_BADGES[linkResult.delivery] && (
              <span
                className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${DELIVERY_BADGES[linkResult.delivery].cls}`}
              >
                {DELIVERY_BADGES[linkResult.delivery].label}
              </span>
            )}
            <div className="flex items-center gap-2 rounded-lg border border-hairline bg-graphite px-3 py-2">
              <LinkSimple size={16} className="shrink-0 text-slatey" />
              <span className="min-w-0 flex-1 truncate text-xs text-bone">
                {absoluteMagicLink(linkResult.magic_link)}
              </span>
              <button
                type="button"
                onClick={() => copyLink(linkResult.magic_link)}
                className="flex shrink-0 items-center gap-1 rounded-full bg-primary px-3 py-1.5 text-xs font-medium text-on-primary hover:opacity-90"
              >
                <Copy size={13} />
                복사
              </button>
            </div>
            <p className="text-xs text-slatey">
              링크는 보안을 위해 화면에만 표시됩니다. 다시 필요하면 목록에서 [재발급]하세요.
            </p>
          </div>
        )}
      </Modal>

      {/* 비활성화 확인 */}
      <ConfirmDialog
        open={!!deactivateTarget}
        title="포털 계정 비활성화"
        message={
          <>
            <b>{deactivateTarget?.email}</b> 계정을 비활성화합니다. 즉시 포털 로그인이 차단됩니다.
          </>
        }
        confirmLabel="비활성화"
        danger
        loading={deactivate.isPending}
        onConfirm={() =>
          deactivateTarget &&
          run(
            () => deactivate.mutateAsync(deactivateTarget.user_id),
            '포털 계정이 비활성화되었습니다.',
            () => setDeactivateTarget(null),
          )
        }
        onCancel={() => setDeactivateTarget(null)}
      />
    </div>
  )
}
