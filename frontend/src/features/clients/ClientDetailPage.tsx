// SCR-03D 고객사 상세 360° 뷰 — 상담 전화 응대를 이 화면 하나로 완결
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Buildings,
  CaretLeft,
  CaretRight,
  Car,
  ChatCircleDots,
  DownloadSimple,
  MagnifyingGlass,
  PencilSimple,
  Phone,
  Plus,
  Trash,
  UploadSimple,
} from '@phosphor-icons/react'
import { StatusBadge } from '../../components/StatusBadge'
import { SensitiveData } from '../../components/SensitiveData'
import { Timeline } from '../../components/Timeline'
import { EmptyState } from '../../components/EmptyState'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useAuth } from '../../app/AuthProvider'
import { Skeleton, SkeletonTableRows } from '../../components/Skeleton'
import { AuditLine } from '../../components/AuditLine'
import { useToast } from '../../components/Toast'
import { DocumentPreviewModal } from '../../components/DocumentPreviewModal'
import { downloadDocument, downloadErrorMessage, previewKind } from '../../lib/download'
import { useCodes } from '../../lib/api/queries'
import { fmtDate, fmtMoney, fmtServerDate, fmtServerDateTime, telHref } from '../../lib/format'
import { useDebounced } from '../../lib/useDebounced'
import type { Client, Document } from '../../types'
import { ActivityForm } from '../histories/ActivityForm'
import { useClientThreads } from '../chat/api'
import { ThreadModePill, ThreadWaitingBadge } from '../chat/ThreadBadges'
import {
  useAddRecipient,
  useClient,
  useClientAssets,
  useClientDocuments,
  useClientHistories,
  useClientRecipients,
  useClientReports,
  useClientVehicles,
  useDeleteClient,
  useRemoveRecipient,
} from './api'
import { ClientAvatar } from './ClientsPage'
import { ClientFormModal } from './ClientFormModal'
import { FleetImportModal } from './FleetImportModal'

type TabKey = 'overview' | 'histories' | 'reports' | 'assets' | 'vehicles' | 'chat'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'overview', label: '개요' },
  { key: 'histories', label: '활동 이력' },
  { key: 'reports', label: '보고서·문서' },
  { key: 'assets', label: '자산 및 연동' },
  { key: 'vehicles', label: '보유 차량' },
  { key: 'chat', label: '상담' },
]

function InfoRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-hairline py-2.5 last:border-b-0 sm:flex-row sm:items-center">
      <dt className="w-40 shrink-0 text-xs font-medium text-slatey">{label}</dt>
      <dd className="text-sm text-bone">{children}</dd>
    </div>
  )
}

export function ClientDetailPage() {
  const { clientId } = useParams<{ clientId: string }>()
  const { data: client, isLoading, isError, refetch } = useClient(clientId)
  const { labelOf: clientTypeLabel } = useCodes('CLIENT_TYPE')

  const [tab, setTab] = useState<TabKey>('overview')
  const [editOpen, setEditOpen] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [forceOpen, setForceOpen] = useState(false)
  const [confirmName, setConfirmName] = useState('')
  const [depDetail, setDepDetail] = useState('')
  const navigate = useNavigate()
  const { showToast } = useToast()
  const { user } = useAuth()
  const deleteClient = useDeleteClient()

  if (isLoading) {
    return (
      <div className="animate-fade-in space-y-4">
        <div className="rounded-3xl border border-hairline bg-graphite p-5">
          <div className="flex items-center gap-3">
            <Skeleton className="h-12 w-12 rounded-lg" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-3 w-72" />
            </div>
          </div>
        </div>
        <div className="rounded-3xl border border-hairline bg-graphite p-5">
          <SkeletonTableRows rows={5} />
        </div>
      </div>
    )
  }

  if (isError || !client) {
    return (
      <EmptyState
        icon={<Buildings size={36} />}
        title="고객사 정보를 불러오지 못했습니다"
        action={
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => refetch()}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
            >
              다시 시도
            </button>
            <Link
              to="/clients"
              className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90"
            >
              목록으로
            </Link>
          </div>
        }
      />
    )
  }

  return (
    <div className="animate-fade-in space-y-4">
      <Link
        to="/clients"
        className="inline-flex items-center gap-1 text-sm text-ash hover:text-bone"
      >
        <ArrowLeft size={14} />
        고객사 목록
      </Link>

      {/* 헤더 카드 */}
      <div className="rounded-3xl border border-hairline bg-graphite p-5">
        <div className="flex flex-wrap items-center gap-4">
          <ClientAvatar name={client.company_name} className="h-12 w-12 rounded-xl text-lg" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg font-bold text-bone">{client.company_name}</h1>
              <span className="text-xs font-medium text-slatey">
                {clientTypeLabel(client.client_type)}
              </span>
              <StatusBadge domain="contract" value={client.contract_status} />
            </div>
            <p className="mt-0.5 text-xs text-slatey">
              {client.biz_reg_no ?? '—'} · {client.region ?? ''} {client.address ?? ''}
            </p>
          </div>
          <div className="flex items-center gap-4">
            {/* 주 담당자 Click-to-Call */}
            <div className="text-right">
              <p className="text-xs text-slatey">주 담당자</p>
              <a
                href={telHref(client.main_contact_phone)}
                className="flex items-center gap-1.5 text-sm font-semibold text-bone hover:underline"
              >
                <Phone size={14} weight="fill" className="text-emerald-500" />
                {client.main_contact_name ?? '—'}
                <span className="font-normal text-ash">
                  {client.main_contact_phone ?? ''}
                </span>
              </a>
            </div>
            <button
              type="button"
              onClick={() => setEditOpen(true)}
              className="hidden items-center gap-1.5 rounded-full border border-hairline px-3 py-2 text-sm font-medium text-bone hover:bg-elevate sm:flex"
            >
              <PencilSimple size={15} />
              수정
            </button>
            <button
              type="button"
              onClick={() => setDeleteOpen(true)}
              className="hidden items-center gap-1.5 rounded-full border border-hairline px-3 py-2 text-sm font-medium text-rose-400 hover:bg-rose-500/10 sm:flex"
            >
              <Trash size={15} />
              삭제
            </button>
          </div>
        </div>
      </div>

      {/* 탭 */}
      <div className="flex gap-1 overflow-x-auto border-b border-hairline">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`shrink-0 border-b-2 px-3.5 py-2.5 text-sm font-medium transition-colors ${
              tab === t.key
                ? 'border-snow text-bone'
                : 'border-transparent text-slatey hover:text-ash'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && <OverviewTab client={client} />}
      {tab === 'histories' && (
        <HistoriesTab clientId={client.client_id} onAdd={() => setActivityOpen(true)} />
      )}
      {tab === 'reports' && <ReportsDocsTab clientId={client.client_id} />}
      {tab === 'assets' && <AssetsTab clientId={client.client_id} />}
      {tab === 'vehicles' && <VehiclesTab clientId={client.client_id} />}
      {tab === 'chat' && <ChatTab clientId={client.client_id} />}

      <ClientFormModal open={editOpen} onClose={() => setEditOpen(false)} client={client} />
      <ActivityForm
        open={activityOpen}
        onClose={() => setActivityOpen(false)}
        defaultClientId={client.client_id}
        lockClient
      />
      <ConfirmDialog
        open={deleteOpen}
        title="고객사 삭제"
        message={
          <>
            <b>{client.company_name}</b> 고객사를 삭제합니다. 이력·사업·자산·수신자 등 연결된
            데이터가 있으면 삭제되지 않으며, 이 경우 계약 상태를 <b>종료</b>로 변경하세요.
          </>
        }
        confirmLabel="삭제"
        danger
        loading={deleteClient.isPending}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={async () => {
          try {
            await deleteClient.mutateAsync({ clientId: client.client_id })
            showToast('고객사가 삭제되었습니다.', 'success')
            setDeleteOpen(false)
            navigate('/clients')
          } catch (err) {
            const e = err as { response?: { status?: number; data?: { detail?: string } } }
            const detail = e?.response?.data?.detail
            if (e?.response?.status === 409) {
              // 종속 데이터로 삭제 불가 → 강제 삭제(담당자 명의 확인) 흐름으로 전환
              setDepDetail(detail || '연결된 데이터가 있습니다.')
              setConfirmName('')
              setDeleteOpen(false)
              setForceOpen(true)
            } else {
              showToast(detail || '삭제에 실패했습니다.', 'danger')
            }
          }
        }}
      />
      <ConfirmDialog
        open={forceOpen}
        title="고객사 강제 삭제"
        message={
          <div className="space-y-2">
            <p>
              <b>{client.company_name}</b> 고객사에 연결된 데이터가 있습니다:
            </p>
            <p className="rounded bg-rose-500/10 px-2 py-1 text-xs text-rose-300">{depDetail}</p>
            <p>
              강제 삭제하면 위 <b>연결 데이터가 함께 영구 삭제</b>됩니다(되돌릴 수 없음). 사업
              참여·정산이 있으면 강제로도 삭제되지 않습니다.
            </p>
            <p className="text-xs text-ash">
              진행하려면 담당자 <b>본인 이름{user?.name ? ` (${user.name})` : ''}</b>을 입력하세요.
            </p>
            <input
              value={confirmName}
              onChange={(e) => setConfirmName(e.target.value)}
              placeholder="담당자 본인 이름"
              className="h-9 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
            />
          </div>
        }
        confirmLabel="강제 삭제"
        danger
        loading={deleteClient.isPending}
        onCancel={() => setForceOpen(false)}
        onConfirm={async () => {
          if (!confirmName.trim()) {
            showToast('담당자 본인 이름을 입력해 주세요.', 'danger')
            return
          }
          try {
            await deleteClient.mutateAsync({
              clientId: client.client_id,
              force: true,
              confirmName: confirmName.trim(),
            })
            showToast('고객사가 강제 삭제되었습니다.', 'success')
            setForceOpen(false)
            navigate('/clients')
          } catch (err) {
            const detail = (err as { response?: { data?: { detail?: string } } })?.response
              ?.data?.detail
            showToast(detail || '강제 삭제에 실패했습니다.', 'danger')
          }
        }}
      />
    </div>
  )
}

// ── 개요 탭 ─────────────────────────────────────────────────────────
function OverviewTab({ client }: { client: Client }) {
  const { labelOf: clientTypeLabel } = useCodes('CLIENT_TYPE')
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* 참여 규모 요약 — ProjectVehicle(참여 차량) 집계 (목록·개요 공통) */}
      <section className="rounded-3xl border border-hairline bg-graphite p-5 lg:col-span-2">
        <h2 className="mb-3 text-sm font-semibold text-bone">참여 규모</h2>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <dt className="text-xs text-slatey">참여 사업</dt>
            <dd className="mt-1 text-lg font-semibold text-bone">
              {(client.participating_project_count ?? 0).toLocaleString()}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slatey">참여 차량</dt>
            <dd className="mt-1 text-lg font-semibold text-bone">
              {(client.participating_vehicle_count ?? 0).toLocaleString()}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slatey">총감축량 (tCO₂)</dt>
            <dd className="mt-1 text-lg font-semibold text-bone">
              {(client.total_reduction ?? 0).toLocaleString()}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slatey">예상지급액</dt>
            <dd className="mt-1 text-lg font-semibold text-bone">
              {client.total_expected_payout != null ? (
                <SensitiveData type="money" value={fmtMoney(client.total_expected_payout)} />
              ) : (
                '—'
              )}
            </dd>
          </div>
        </dl>
      </section>

      <section className="rounded-3xl border border-hairline bg-graphite p-5">
        <h2 className="mb-2 text-sm font-semibold text-bone">기본 정보</h2>
        <dl>
          <InfoRow label="고객사명">{client.company_name}</InfoRow>
          <InfoRow label="구분">{clientTypeLabel(client.client_type)}</InfoRow>
          <InfoRow label="사업자번호">{client.biz_reg_no ?? '—'}</InfoRow>
          <InfoRow label="지역 / 주소">
            {client.region ?? '—'} / {client.address ?? '—'}
          </InfoRow>
          <InfoRow label="대표자">{client.ceo_name ?? '—'}</InfoRow>
          <InfoRow label="대표 연락처">
            {client.ceo_contact_phone ? (
              <SensitiveData type="text" value={client.ceo_contact_phone} />
            ) : (
              '—'
            )}
          </InfoRow>
          <InfoRow label="대표 이메일">{client.ceo_contact_email ?? '—'}</InfoRow>
          <InfoRow label="키맨 (주요 결정권자)">{client.keyman ?? '—'}</InfoRow>
        </dl>
      </section>

      <section className="rounded-3xl border border-hairline bg-graphite p-5">
        <h2 className="mb-2 text-sm font-semibold text-bone">계약·담당·보고서</h2>
        <dl>
          <InfoRow label="계약 상태">
            <StatusBadge domain="contract" value={client.contract_status} />
          </InfoRow>
          <InfoRow label="계약 일자">{fmtDate(client.contract_date)}</InfoRow>
          <InfoRow label="담당 PM">{client.manager_name ?? '—'}</InfoRow>
          <InfoRow label="주 담당자">
            {client.main_contact_name ?? '—'}{' '}
            <a
              href={telHref(client.main_contact_phone)}
              className="ml-1 text-ash hover:underline"
            >
              {client.main_contact_phone ?? ''}
            </a>
          </InfoRow>
          <InfoRow label="담당자 이메일 (발송 기준)">{client.main_contact_email ?? '—'}</InfoRow>
          <InfoRow label="월간 보고서 수신">
            {client.report_yn === 'Y' ? '수신 (Y)' : '미수신 (N)'}
          </InfoRow>
          {(client.subscriptions ?? []).map((sub) => (
            <InfoRow key={sub.sub_id} label="구독 설정">
              {sub.report_type} · {sub.channel === 'BOTH' ? '이메일+카카오' : sub.channel === 'KAKAO' ? '카카오' : '이메일'}
              {sub.due_day ? ` · 매월 ${sub.due_day}일 마감` : ''}
              {sub.active !== 'Y' ? ' (비활성)' : ''}
            </InfoRow>
          ))}
        </dl>
        <AuditLine createdAt={client.created_at} updatedAt={client.updated_at} className="mt-3" />
      </section>

      <RecipientsSection client={client} />
    </div>
  )
}

// ── 보고서 수신자 (tb_report_recipient, R2-B8) ──────────────────────
// 발송 해석 규칙(resolve_recipients): 수신자 미등록 시 주 담당자 이메일 폴백.
function RecipientsSection({ client }: { client: Client }) {
  const { showToast } = useToast()
  const { data: recipients = [], isLoading } = useClientRecipients(client.client_id)
  const addRecipient = useAddRecipient(client.client_id)
  const removeRecipient = useRemoveRecipient(client.client_id)

  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [ccYn, setCcYn] = useState(false)

  // sub_id → 보고서 유형 라벨 (구독 지정분 표기)
  const subTypeOf = (subId?: string | null) =>
    (client.subscriptions ?? []).find((s) => s.sub_id === subId)?.report_type

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault()
    if (!email.trim()) return
    try {
      await addRecipient.mutateAsync({
        email: email.trim(),
        ...(name.trim() ? { name: name.trim() } : {}),
        cc_yn: ccYn ? 'Y' : 'N',
      })
      setEmail('')
      setName('')
      setCcYn(false)
      showToast('수신자가 추가되었습니다.', 'success')
    } catch (err) {
      // 409(중복)·422(형식) — 서버 detail을 그대로 노출
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      showToast(detail ?? '수신자 추가에 실패했습니다.', 'danger')
    }
  }

  const handleRemove = async (recipientId: string, label: string) => {
    try {
      await removeRecipient.mutateAsync(recipientId)
      showToast(`${label} 수신자가 삭제되었습니다.`, 'success')
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      showToast(detail ?? '수신자 삭제에 실패했습니다.', 'danger')
    }
  }

  return (
    <section className="rounded-3xl border border-hairline bg-graphite p-5 lg:col-span-2">
      <h2 className="mb-1 text-sm font-semibold text-bone">보고서 수신자</h2>
      <p className="mb-3 text-xs text-slatey">
        월간 보고서 이메일 수신 목록 — 수신자가 없으면 주 담당자 이메일(
        {client.main_contact_email ?? '미등록'})로 발송됩니다.
      </p>

      {isLoading ? (
        <SkeletonTableRows rows={2} />
      ) : recipients.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-hairline py-4 text-center text-xs text-slatey">
          등록된 수신자가 없습니다 — 발송 시 주 담당자 이메일로 발송됩니다
        </p>
      ) : (
        <ul className="divide-y divide-hairline rounded-2xl border border-hairline">
          {recipients.map((r) => (
            <li key={r.recipient_id} className="flex items-center gap-2.5 px-3 py-2">
              <span
                className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${
                  r.cc_yn === 'Y'
                    ? 'bg-elevate-strong text-ash'
                    : 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                }`}
              >
                {r.cc_yn === 'Y' ? 'CC' : 'TO'}
              </span>
              <span className="min-w-0 flex-1 truncate text-sm text-bone">
                {r.name ? `${r.name} ` : ''}
                <span className={r.name ? 'text-ash' : undefined}>{r.email}</span>
              </span>
              <span className="shrink-0 rounded bg-elevate-strong px-1.5 py-0.5 text-[10px] font-medium text-ash">
                {r.sub_id ? `${subTypeOf(r.sub_id) ?? '구독'} 지정` : '공통'}
              </span>
              <button
                type="button"
                onClick={() => void handleRemove(r.recipient_id, r.name ?? r.email)}
                disabled={removeRecipient.isPending}
                className="shrink-0 rounded-lg p-1.5 text-smoke hover:bg-elevate hover:text-rose-400 disabled:opacity-50"
                title="삭제"
                aria-label={`${r.email} 삭제`}
              >
                <Trash size={15} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* 추가 폼 — 이메일 필수, 이름 선택, CC 토글 */}
      <form onSubmit={handleAdd} className="mt-3 flex flex-wrap items-center gap-2">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="이메일 (필수)"
          required
          className="h-9 min-w-[180px] flex-1 rounded-lg border border-hairline bg-elevate px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="이름 (선택)"
          className="h-9 w-32 rounded-lg border border-hairline bg-elevate px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
        />
        <label className="flex cursor-pointer items-center gap-1.5 text-xs font-medium text-ash">
          <input
            type="checkbox"
            checked={ccYn}
            onChange={(e) => setCcYn(e.target.checked)}
            className="h-4 w-4 accent-emerald-500"
          />
          참조(CC)로 받기
        </label>
        <button
          type="submit"
          disabled={addRecipient.isPending || !email.trim()}
          className="flex items-center gap-1 rounded-full bg-primary px-3 py-1.5 text-xs font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
        >
          <Plus size={13} weight="bold" />
          수신자 추가
        </button>
      </form>
    </section>
  )
}

// ── 활동 이력 탭 ────────────────────────────────────────────────────
function HistoriesTab({ clientId, onAdd }: { clientId: string; onAdd: () => void }) {
  const { data: histories = [], isLoading } = useClientHistories(clientId)
  // 현장 첨부(사진·서명) — 고객사 문서 1회 조회 후 history_id별 매핑 (N+1 금지)
  const { data: documents = [] } = useClientDocuments(clientId)
  const documentsByHistory = useMemo(() => {
    const map: Record<string, Document[]> = {}
    documents.forEach((d) => {
      if (!d.history_id) return
      ;(map[d.history_id] ??= []).push(d)
    })
    return map
  }, [documents])

  return (
    <section className="rounded-3xl border border-hairline bg-graphite p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-bone">활동 이력 (시간 역순)</h2>
        <button
          type="button"
          onClick={onAdd}
          className="flex items-center gap-1 rounded-full bg-primary px-3 py-1.5 text-xs font-medium text-on-primary hover:opacity-90"
        >
          <Plus size={13} weight="bold" />
          이력 등록
        </button>
      </div>
      {isLoading ? (
        <SkeletonTableRows rows={4} />
      ) : histories.length === 0 ? (
        <EmptyState title="활동 이력이 없습니다" description="첫 컨택 기록을 등록해 보세요." />
      ) : (
        <Timeline items={histories} showClient={false} documentsByHistory={documentsByHistory} />
      )}
    </section>
  )
}

// ── 보고서·문서 탭 ──────────────────────────────────────────────────
function ReportsDocsTab({ clientId }: { clientId: string }) {
  const { data: reports = [], isLoading: reportsLoading } = useClientReports(clientId)
  const { data: documents = [], isLoading: docsLoading } = useClientDocuments(clientId)
  const { showToast } = useToast()
  // 문서명 클릭 → 미리보기(이미지/PDF만) — 다운로드 아이콘은 별도 유지
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null)

  // 다운로드 실패(404/503 등) 시 에러 토스트 (L-3)
  const handleDownload = async (docId: string, title?: string) => {
    try {
      await downloadDocument(docId, title)
    } catch (err) {
      showToast(downloadErrorMessage(err), 'danger')
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="rounded-3xl border border-hairline bg-graphite p-5">
        <h2 className="mb-3 text-sm font-semibold text-bone">월간 보고서 발송 이력</h2>
        {reportsLoading ? (
          <SkeletonTableRows rows={3} />
        ) : reports.length === 0 ? (
          <EmptyState title="보고서 발송 이력이 없습니다" />
        ) : (
          <ul className="divide-y divide-hairline">
            {reports.map((r) => (
              <li key={r.report_id} className="flex items-center gap-3 py-2.5">
                <span className="w-16 shrink-0 font-mono text-xs text-ash">{r.period}</span>
                <span className="min-w-0 flex-1 truncate text-sm text-bone">
                  {r.report_type}
                </span>
                <span className="text-xs text-slatey">{fmtServerDate(r.sent_at)}</span>
                <StatusBadge domain="report" value={r.status} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-3xl border border-hairline bg-graphite p-5">
        <h2 className="mb-3 text-sm font-semibold text-bone">고객사 문서함</h2>
        {docsLoading ? (
          <SkeletonTableRows rows={3} />
        ) : documents.length === 0 ? (
          <EmptyState title="등록된 문서가 없습니다" />
        ) : (
          <ul className="divide-y divide-hairline">
            {documents.map((d) => (
              <li key={d.doc_id} className="flex items-center gap-3 py-2.5">
                <div className="min-w-0 flex-1">
                  {previewKind(d) ? (
                    <button
                      type="button"
                      onClick={() => setPreviewDoc(d)}
                      className="block max-w-full truncate text-left text-sm font-medium text-bone hover:underline"
                      title="미리보기"
                    >
                      {d.title}
                    </button>
                  ) : (
                    <p className="truncate text-sm font-medium text-bone">{d.title}</p>
                  )}
                  <p className="text-xs text-slatey">
                    {d.doc_type} · v{d.version} · {fmtServerDateTime(d.created_at)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void handleDownload(d.doc_id, d.title)}
                  className="rounded-lg p-1.5 text-smoke hover:bg-elevate hover:text-bone"
                  title="다운로드"
                >
                  <DownloadSimple size={16} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <DocumentPreviewModal doc={previewDoc} onClose={() => setPreviewDoc(null)} />
    </div>
  )
}

// ── 상담 탭 (SCR-08 딥링크) ─────────────────────────────────────────
function ChatTab({ clientId }: { clientId: string }) {
  const { data: threads = [], isLoading } = useClientThreads(clientId)

  return (
    <section className="rounded-3xl border border-hairline bg-graphite p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-bone">카카오톡 상담 스레드 (최근순)</h2>
        <Link
          to={`/chat?client=${clientId}`}
          className="flex items-center gap-1 rounded-full bg-primary px-3 py-1.5 text-xs font-medium text-on-primary hover:opacity-90"
        >
          <ChatCircleDots size={13} weight="fill" />
          상담 관제에서 열기
        </Link>
      </div>
      {isLoading ? (
        <SkeletonTableRows rows={3} />
      ) : threads.length === 0 ? (
        <EmptyState
          icon={<ChatCircleDots size={36} />}
          title="상담 이력이 없습니다"
          description="카카오 채널 연동 후 상담 이력이 표시됩니다."
        />
      ) : (
        <ul className="divide-y divide-hairline">
          {threads.map((t) => (
            <li key={t.thread_id}>
              <Link
                to={`/chat?client=${clientId}`}
                className="flex items-center gap-3 rounded-md px-1 py-2.5 hover:bg-elevate"
              >
                <ThreadModePill thread={t} />
                <ThreadWaitingBadge thread={t} />
                <span className="min-w-0 flex-1 truncate text-sm text-bone">
                  {t.last_message_preview ?? '메시지가 없습니다'}
                </span>
                <span className="shrink-0 text-xs text-slatey">
                  {fmtServerDateTime(t.last_message_at)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

// ── 참여 사업·정산 탭 (SCR-06/07 축약형) ────────────────────────────
// ── 자산 및 연동 탭 (SCR-04 축약형) ─────────────────────────────────
function AssetsTab({ clientId }: { clientId: string }) {
  const { data: assets = [], isLoading } = useClientAssets(clientId)

  return (
    <section className="rounded-3xl border border-hairline bg-graphite p-5">
      <h2 className="mb-3 text-sm font-semibold text-bone">자산·연동 마스터</h2>
      {isLoading ? (
        <SkeletonTableRows rows={3} />
      ) : assets.length === 0 ? (
        <EmptyState
          title="등록된 자산이 없습니다"
          description="자산 등록·연동 관리는 '자산·연동 마스터' 화면에서 제공됩니다."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-max text-left text-sm">
            <thead>
              <tr className="border-b border-hairline text-xs font-semibold text-ash">
                <th className="px-3 py-2">자산 분류</th>
                <th className="px-3 py-2">제원</th>
                <th className="px-3 py-2">수량</th>
                <th className="px-3 py-2">관제 연동</th>
                <th className="px-3 py-2">대상 기관</th>
                <th className="px-3 py-2">접속 정보</th>
                <th className="px-3 py-2">상태</th>
              </tr>
            </thead>
            <tbody>
              {assets.map((a) => (
                <tr key={a.asset_id} className="border-b border-hairline last:border-b-0">
                  <td className="px-3 py-2.5">
                    {a.asset_type ? (
                      <StatusBadge domain="assetType" value={a.asset_type} />
                    ) : (
                      <span className="text-xs text-slatey">{a.asset_group}</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-ash">{a.main_spec ?? '—'}</td>
                  <td className="px-3 py-2.5 text-ash">{a.quantity ?? '—'}</td>
                  <td className="px-3 py-2.5 text-xs">
                    {a.telemetry_yn === 'Y' ? (
                      <span className="font-semibold text-emerald-400">Y</span>
                    ) : (
                      <span className="text-slatey">N</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-ash">{a.agency_name ?? '—'}</td>
                  <td className="px-3 py-2.5">
                    {a.login_id ? (
                      <SensitiveData type="secret" value={a.login_id} />
                    ) : (
                      <span className="text-slatey">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    {a.status ? <StatusBadge domain="assetStatus" value={a.status} /> : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

// ── 보유 차량 탭 (tb_client_vehicle, 부록 M) ────────────────────────
// 운수사 보유 차량 마스터 + 감축사업 참여 구분. 명부 업로드는 전국 단위(전역 fleet).
const CLIENT_VEHICLE_PAGE_SIZE = 50
const PARTICIPATION_TABS: { key: string; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: 'participating', label: '참여' },
  { key: 'unassigned', label: '미참여' },
]

function VehiclesTab({ clientId }: { clientId: string }) {
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)
  const [participation, setParticipation] = useState('all')
  const [page, setPage] = useState(1)
  useEffect(() => {
    setPage(1) // 검색어·필터 변경 시 첫 페이지로
  }, [debouncedSearch, participation])
  const { data } = useClientVehicles(clientId, {
    page,
    pageSize: CLIENT_VEHICLE_PAGE_SIZE,
    q: debouncedSearch,
    participation,
  })
  // 총건수가 줄어 현재 페이지가 범위를 벗어나면 마지막 페이지로 클램프
  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil((data?.total ?? 0) / CLIENT_VEHICLE_PAGE_SIZE))
    if (page > maxPage) setPage(maxPage)
  }, [data?.total, page])
  const { labelOf: introLabel } = useCodes('VEHICLE_INTRO')
  const [fleetModalOpen, setFleetModalOpen] = useState(false)
  const vehicles = data?.items ?? []

  return (
    <section className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-baseline gap-3">
          <h2 className="text-sm font-semibold text-bone">보유 차량</h2>
          {data && (
            <span className="text-xs text-slatey">
              총 {data.total.toLocaleString()}대 · 참여{' '}
              {data.participating_count.toLocaleString()} / 미참여{' '}
              {data.unassigned_count.toLocaleString()}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 self-start">
          <button
            type="button"
            onClick={() => setFleetModalOpen(true)}
            className="flex items-center gap-1.5 rounded-full border border-hairline px-3 py-2 text-sm font-medium text-bone hover:bg-elevate"
          >
            <UploadSimple size={15} />
            전국 버스 명부 업로드
          </button>
        </div>
      </div>

      <FleetImportModal
        open={fleetModalOpen}
        onClose={() => setFleetModalOpen(false)}
        clientId={clientId}
      />

      {/* 필터 세그먼트 + 검색(차량번호) */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex gap-1 rounded-full border border-hairline p-0.5">
          {PARTICIPATION_TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setParticipation(t.key)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                participation === t.key
                  ? 'bg-elevate text-bone'
                  : 'text-slatey hover:text-ash'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="relative w-full sm:max-w-xs">
          <MagnifyingGlass
            size={15}
            className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-slatey"
          />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="차량번호 검색…"
            className="w-full rounded-md border border-hairline bg-graphite py-2 pr-3 pl-9 text-sm text-bone outline-none placeholder:text-slatey focus:border-white/30"
            aria-label="차량 검색"
          />
        </div>
      </div>

      {vehicles.length === 0 ? (
        <EmptyState
          icon={<Car size={36} />}
          title={
            debouncedSearch || participation !== 'all'
              ? '조건에 맞는 차량이 없습니다'
              : '등록된 보유 차량이 없습니다'
          }
          description={
            debouncedSearch || participation !== 'all'
              ? '다른 검색어·필터로 다시 시도해 보세요.'
              : '[전국 버스 명부 업로드]로 차량 명부를 반영하면 여기에 표시됩니다.'
          }
          className="py-8"
        />
      ) : (
        <div className="overflow-x-auto rounded-3xl border border-hairline bg-graphite">
          <table className="w-full min-w-[880px] text-sm">
            <thead>
              <tr className="border-b border-hairline text-xs text-slatey">
                <th className="px-3 py-2.5 text-left font-semibold">차량번호</th>
                <th className="px-3 py-2.5 text-left font-semibold">지역</th>
                <th className="px-3 py-2.5 text-left font-semibold">차명</th>
                <th className="px-3 py-2.5 text-left font-semibold">차종</th>
                <th className="px-3 py-2.5 text-right font-semibold">연식</th>
                <th className="px-3 py-2.5 text-left font-semibold">등록일</th>
                <th className="px-3 py-2.5 text-left font-semibold">연료</th>
                <th className="px-3 py-2.5 text-right font-semibold">승차정원</th>
                <th className="px-3 py-2.5 text-left font-semibold">참여</th>
                <th className="px-3 py-2.5 text-right font-semibold">잔여반영감축량</th>
                <th className="px-3 py-2.5 text-right font-semibold">예상지급액</th>
              </tr>
            </thead>
            <tbody>
              {vehicles.map((v) => (
                <tr key={v.vehicle_id} className="border-b border-hairline/60 last:border-b-0">
                  <td className="px-3 py-2.5 font-medium text-bone">{v.vehicle_no ?? '—'}</td>
                  <td className="px-3 py-2.5 text-ash">{v.region ?? '—'}</td>
                  <td className="px-3 py-2.5 text-ash">{v.model_name ?? '—'}</td>
                  <td className="px-3 py-2.5 text-ash">{v.vehicle_class ?? '—'}</td>
                  <td className="px-3 py-2.5 text-right text-ash">{v.model_year ?? '—'}</td>
                  <td className="px-3 py-2.5 text-ash">{fmtServerDate(v.registered_at)}</td>
                  <td className="px-3 py-2.5 text-ash">{v.fuel ?? '—'}</td>
                  <td className="px-3 py-2.5 text-right text-ash">
                    {v.seating_capacity ?? '—'}
                  </td>
                  <td className="px-3 py-2.5">
                    {v.participation ? (
                      v.project_id ? (
                        <Link
                          to={`/projects/${v.project_id}`}
                          className="inline-flex items-center rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-700 hover:underline dark:text-emerald-300"
                        >
                          {v.project_name ?? '참여'}
                          {v.introduction_type ? ` · ${introLabel(v.introduction_type)}` : ''}
                        </Link>
                      ) : (
                        <span className="inline-flex items-center rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-300">
                          참여
                        </span>
                      )
                    ) : (
                      <span className="inline-flex items-center rounded-full bg-elevate-strong px-2 py-0.5 text-xs font-medium text-slatey">
                        미참여
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-right text-ash">
                    {v.effective_reduction != null
                      ? v.effective_reduction.toLocaleString()
                      : '—'}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    {v.expected_payout != null ? (
                      <SensitiveData type="money" value={fmtMoney(v.expected_payout)} />
                    ) : (
                      <span className="text-slatey">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 페이지네이션 */}
      {(data?.total ?? 0) > CLIENT_VEHICLE_PAGE_SIZE && (
        <div className="flex items-center justify-between text-xs text-slatey">
          <span>
            {(page - 1) * CLIENT_VEHICLE_PAGE_SIZE + 1}–
            {(page - 1) * CLIENT_VEHICLE_PAGE_SIZE + vehicles.length} / 총{' '}
            {data?.total.toLocaleString()}대
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="rounded-md border border-hairline p-1.5 text-bone hover:bg-elevate disabled:opacity-40"
              aria-label="이전 페이지"
            >
              <CaretLeft size={14} />
            </button>
            <span className="px-1">
              {page} / {Math.max(1, Math.ceil((data?.total ?? 0) / CLIENT_VEHICLE_PAGE_SIZE))}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => p + 1)}
              disabled={page >= Math.ceil((data?.total ?? 0) / CLIENT_VEHICLE_PAGE_SIZE)}
              className="rounded-md border border-hairline p-1.5 text-bone hover:bg-elevate disabled:opacity-40"
              aria-label="다음 페이지"
            >
              <CaretRight size={14} />
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
