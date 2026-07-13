// SCR-03D 고객사 상세 360° 뷰 — 상담 전화 응대를 이 화면 하나로 완결
import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Buildings,
  ChatCircleDots,
  DownloadSimple,
  PencilSimple,
  Phone,
  Plus,
  TreeStructure,
} from '@phosphor-icons/react'
import { StatusBadge } from '../../components/StatusBadge'
import { SensitiveData } from '../../components/SensitiveData'
import { Timeline } from '../../components/Timeline'
import { EmptyState } from '../../components/EmptyState'
import { Skeleton, SkeletonTableRows } from '../../components/Skeleton'
import { AuditLine } from '../../components/AuditLine'
import { useToast } from '../../components/Toast'
import { downloadDocument, downloadErrorMessage } from '../../lib/download'
import { fmtDate, fmtServerDate, fmtServerDateTime, telHref } from '../../lib/format'
import type { Client } from '../../types'
import { ActivityForm } from '../histories/ActivityForm'
import { useClientThreads } from '../chat/api'
import { ThreadModePill, ThreadWaitingBadge } from '../chat/ThreadBadges'
import {
  useClient,
  useClientAssets,
  useClientDocuments,
  useClientHistories,
  useClientReports,
} from './api'
import { ClientAvatar } from './ClientsPage'
import { ClientFormModal } from './ClientFormModal'

type TabKey = 'overview' | 'histories' | 'reports' | 'assets' | 'projects' | 'chat'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'overview', label: '개요' },
  { key: 'histories', label: '활동 이력' },
  { key: 'reports', label: '보고서·문서' },
  { key: 'assets', label: '자산 및 연동' },
  { key: 'projects', label: '참여 사업·정산' },
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

  const [tab, setTab] = useState<TabKey>('overview')
  const [editOpen, setEditOpen] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)

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
                {client.client_type === 'TRANSPORT' ? '운수사' : '건물·농장'}
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
            <div className="text-right">
              <p className="text-xs text-slatey">성공 보수율</p>
              {client.success_fee_rate != null ? (
                <SensitiveData
                  type="rate"
                  value={`${client.success_fee_rate} %`}
                  className="text-sm font-semibold"
                />
              ) : (
                <span className="text-sm text-slatey">—</span>
              )}
            </div>
            <button
              type="button"
              onClick={() => setEditOpen(true)}
              className="hidden items-center gap-1.5 rounded-full border border-hairline px-3 py-2 text-sm font-medium text-bone hover:bg-elevate sm:flex"
            >
              <PencilSimple size={15} />
              수정
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
      {tab === 'projects' && (
        <EmptyState
          icon={<TreeStructure size={36} />}
          title="참여 사업·정산은 P2에서 제공됩니다"
          description="감축 사업 관리(SCR-06)·정산 현황(SCR-07) 구축 시 이 탭에서 사업·지분율·예상 정산액을 확인할 수 있습니다."
        />
      )}
      {tab === 'chat' && <ChatTab clientId={client.client_id} />}

      <ClientFormModal open={editOpen} onClose={() => setEditOpen(false)} client={client} />
      <ActivityForm
        open={activityOpen}
        onClose={() => setActivityOpen(false)}
        defaultClientId={client.client_id}
        lockClient
      />
    </div>
  )
}

// ── 개요 탭 ─────────────────────────────────────────────────────────
function OverviewTab({ client }: { client: Client }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="rounded-3xl border border-hairline bg-graphite p-5">
        <h2 className="mb-2 text-sm font-semibold text-bone">기본 정보</h2>
        <dl>
          <InfoRow label="고객사명">{client.company_name}</InfoRow>
          <InfoRow label="구분">
            {client.client_type === 'TRANSPORT' ? '운수사 (TRANSPORT)' : '건물·농장 (FACILITY)'}
          </InfoRow>
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
          <InfoRow label="keyman">{client.keyman ?? '—'}</InfoRow>
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
    </div>
  )
}

// ── 활동 이력 탭 ────────────────────────────────────────────────────
function HistoriesTab({ clientId, onAdd }: { clientId: string; onAdd: () => void }) {
  const { data: histories = [], isLoading } = useClientHistories(clientId)

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
        <Timeline items={histories} showClient={false} />
      )}
    </section>
  )
}

// ── 보고서·문서 탭 ──────────────────────────────────────────────────
function ReportsDocsTab({ clientId }: { clientId: string }) {
  const { data: reports = [], isLoading: reportsLoading } = useClientReports(clientId)
  const { data: documents = [], isLoading: docsLoading } = useClientDocuments(clientId)
  const { showToast } = useToast()

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
                  <p className="truncate text-sm font-medium text-bone">{d.title}</p>
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

// ── 자산 및 연동 탭 (SCR-04 축약형) ─────────────────────────────────
function AssetsTab({ clientId }: { clientId: string }) {
  const { data: assets = [], isLoading } = useClientAssets(clientId)

  return (
    <section className="rounded-3xl border border-hairline bg-graphite p-5">
      <h2 className="mb-3 text-sm font-semibold text-bone">자산 및 연동 현황</h2>
      {isLoading ? (
        <SkeletonTableRows rows={3} />
      ) : assets.length === 0 ? (
        <EmptyState
          title="등록된 자산이 없습니다"
          description="자산 등록·연동 관리는 P2(SCR-04)에서 제공됩니다."
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
