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
import { downloadDocument } from '../../lib/download'
import { fmtDate, fmtDateTime, telHref } from '../../lib/format'
import type { Client } from '../../types'
import { ActivityForm } from '../histories/ActivityForm'
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
    <div className="flex flex-col gap-0.5 border-b border-slate-50 py-2.5 last:border-b-0 sm:flex-row sm:items-center">
      <dt className="w-40 shrink-0 text-xs font-medium text-slate-400">{label}</dt>
      <dd className="text-sm text-slate-700">{children}</dd>
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
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <Skeleton className="h-12 w-12 rounded-lg" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-5 w-48" />
              <Skeleton className="h-3 w-72" />
            </div>
          </div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
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
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              다시 시도
            </button>
            <Link
              to="/clients"
              className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700"
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
        className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"
      >
        <ArrowLeft size={14} />
        고객사 목록
      </Link>

      {/* 헤더 카드 */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center gap-4">
          <ClientAvatar name={client.company_name} className="h-12 w-12 rounded-xl text-lg" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg font-bold text-slate-900">{client.company_name}</h1>
              <span className="text-xs font-medium text-slate-400">
                {client.client_type === 'TRANSPORT' ? '운수사' : '건물·농장'}
              </span>
              <StatusBadge domain="contract" value={client.contract_status} />
            </div>
            <p className="mt-0.5 text-xs text-slate-400">
              {client.biz_reg_no ?? '—'} · {client.region ?? ''} {client.address ?? ''}
            </p>
          </div>
          <div className="flex items-center gap-4">
            {/* 주 담당자 Click-to-Call */}
            <div className="text-right">
              <p className="text-xs text-slate-400">주 담당자</p>
              <a
                href={telHref(client.main_contact_phone)}
                className="flex items-center gap-1.5 text-sm font-semibold text-slate-800 hover:underline"
              >
                <Phone size={14} weight="fill" className="text-emerald-500" />
                {client.main_contact_name ?? '—'}
                <span className="font-normal text-slate-500">
                  {client.main_contact_phone ?? ''}
                </span>
              </a>
            </div>
            <div className="text-right">
              <p className="text-xs text-slate-400">성공 보수율</p>
              {client.success_fee_rate != null ? (
                <SensitiveData
                  type="rate"
                  value={`${client.success_fee_rate} %`}
                  className="text-sm font-semibold"
                />
              ) : (
                <span className="text-sm text-slate-300">—</span>
              )}
            </div>
            <button
              type="button"
              onClick={() => setEditOpen(true)}
              className="hidden items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 sm:flex"
            >
              <PencilSimple size={15} />
              수정
            </button>
          </div>
        </div>
      </div>

      {/* 탭 */}
      <div className="flex gap-1 overflow-x-auto border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`shrink-0 border-b-2 px-3.5 py-2.5 text-sm font-medium transition-colors ${
              tab === t.key
                ? 'border-slate-800 text-slate-900'
                : 'border-transparent text-slate-400 hover:text-slate-600'
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
      {tab === 'chat' && (
        <EmptyState
          icon={<ChatCircleDots size={36} />}
          title="카카오 상담은 P3에서 제공됩니다"
          description="카카오톡 상담 관제(SCR-08) 구축 시 이 고객사의 상담 스레드로 바로 이동할 수 있습니다."
        />
      )}

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
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-2 text-sm font-semibold text-slate-800">기본 정보</h2>
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

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-2 text-sm font-semibold text-slate-800">계약·담당·보고서</h2>
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
              className="ml-1 text-slate-500 hover:underline"
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
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-800">활동 이력 (시간 역순)</h2>
        <button
          type="button"
          onClick={onAdd}
          className="flex items-center gap-1 rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700"
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

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-slate-800">월간 보고서 발송 이력</h2>
        {reportsLoading ? (
          <SkeletonTableRows rows={3} />
        ) : reports.length === 0 ? (
          <EmptyState title="보고서 발송 이력이 없습니다" />
        ) : (
          <ul className="divide-y divide-slate-50">
            {reports.map((r) => (
              <li key={r.report_id} className="flex items-center gap-3 py-2.5">
                <span className="w-16 shrink-0 font-mono text-xs text-slate-500">{r.period}</span>
                <span className="min-w-0 flex-1 truncate text-sm text-slate-700">
                  {r.report_type}
                </span>
                <span className="text-xs text-slate-400">{fmtDate(r.sent_at)}</span>
                <StatusBadge domain="report" value={r.status} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-slate-800">고객사 문서함</h2>
        {docsLoading ? (
          <SkeletonTableRows rows={3} />
        ) : documents.length === 0 ? (
          <EmptyState title="등록된 문서가 없습니다" />
        ) : (
          <ul className="divide-y divide-slate-50">
            {documents.map((d) => (
              <li key={d.doc_id} className="flex items-center gap-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-700">{d.title}</p>
                  <p className="text-xs text-slate-400">
                    {d.doc_type} · v{d.version} · {fmtDateTime(d.created_at)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => downloadDocument(d.doc_id, d.title)}
                  className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
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

// ── 자산 및 연동 탭 (SCR-04 축약형) ─────────────────────────────────
function AssetsTab({ clientId }: { clientId: string }) {
  const { data: assets = [], isLoading } = useClientAssets(clientId)

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-slate-800">자산 및 연동 현황</h2>
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
              <tr className="border-b border-slate-100 text-xs font-semibold text-slate-500">
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
                <tr key={a.asset_id} className="border-b border-slate-50 last:border-b-0">
                  <td className="px-3 py-2.5">
                    {a.asset_type ? (
                      <StatusBadge domain="assetType" value={a.asset_type} />
                    ) : (
                      <span className="text-xs text-slate-400">{a.asset_group}</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-slate-600">{a.main_spec ?? '—'}</td>
                  <td className="px-3 py-2.5 text-slate-600">{a.quantity ?? '—'}</td>
                  <td className="px-3 py-2.5 text-xs">
                    {a.telemetry_yn === 'Y' ? (
                      <span className="font-semibold text-emerald-600">Y</span>
                    ) : (
                      <span className="text-slate-400">N</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-slate-600">{a.agency_name ?? '—'}</td>
                  <td className="px-3 py-2.5">
                    {a.login_id ? (
                      <SensitiveData type="secret" value={a.login_id} />
                    ) : (
                      <span className="text-slate-300">—</span>
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
