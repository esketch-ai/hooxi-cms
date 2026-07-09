// SCR-14 감사 로그 탭 (ADMIN 전용) — tb_audit_log 조회 (GAN A10)
// 필터(액션 유형·기간) + 테이블(시각·액션 배지·대상·수행자) + 페이지네이션
import { useState } from 'react'
import { ClipboardText } from '@phosphor-icons/react'
import { DataTable, type Column } from '../../components/DataTable'
import { EmptyState } from '../../components/EmptyState'
import { FilterBar, FilterSelect } from '../../components/FilterBar'
import { Pagination } from '../../components/Pagination'
import { fmtDate, fmtTime } from '../../lib/format'
import { useAuditLogs, type AuditLogItem } from './api'

const PAGE_SIZE = 20

// 액션 한국어 라벨 + 배지 톤
const ACTION_SPECS: Record<string, { label: string; cls: string }> = {
  REVEAL_AUTH: { label: '인증정보 열람', cls: 'bg-rose-50 text-rose-700 border-rose-200' },
  SETTLEMENT_CHANGE: {
    label: '정산 상태 변경',
    cls: 'bg-amber-50 text-amber-700 border-amber-200',
  },
  REPORT_VIEW: { label: '보고서 열람', cls: 'bg-blue-50 text-blue-700 border-blue-200' },
  KAKAO_APPROVAL: {
    label: '카카오 연락처 승인',
    cls: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  },
  CONFIG_CHANGE: { label: '설정 변경', cls: 'bg-purple-50 text-purple-700 border-purple-200' },
  // 내부 사용자 감사 이력 (SCR-14 계정 관리)
  USER_APPROVE: { label: '가입 승인', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  USER_ROLE_CHANGE: { label: '역할 변경', cls: 'bg-indigo-50 text-indigo-700 border-indigo-200' },
  USER_DEACTIVATE: { label: '계정 비활성화', cls: 'bg-rose-50 text-rose-700 border-rose-200' },
  USER_PIN_RESET: { label: 'PIN 초기화', cls: 'bg-slate-100 text-slate-700 border-slate-200' },
  DOCUMENT_DOWNLOAD: { label: '문서 다운로드', cls: 'bg-sky-50 text-sky-700 border-sky-200' },
}

const FALLBACK_SPEC = { label: '', cls: 'bg-slate-100 text-slate-600 border-slate-200' }

const TARGET_TYPE_LABELS: Record<string, string> = {
  ASSET: '자산',
  CLIENT: '고객사',
  USER: '사용자',
  REPORT: '보고서',
  SETTLEMENT: '정산',
  CONFIG: '설정',
  KAKAO_CONTACT: '카카오 연락처',
  PROJECT_CLIENT_MAP: '정산 매핑',
  DOCUMENT: '문서',
}

function ActionBadge({ action }: { action: string }) {
  const spec = ACTION_SPECS[action] ?? { ...FALLBACK_SPEC, label: action }
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${spec.cls}`}
    >
      {spec.label || action}
    </span>
  )
}

export function AuditLogTab() {
  const [action, setAction] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(1)

  const { data, isLoading, isError, refetch } = useAuditLogs({
    action: action || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    page,
    page_size: PAGE_SIZE,
  })

  const resetPage = () => setPage(1)

  const columns: Column<AuditLogItem>[] = [
    {
      key: 'created_at',
      header: '시각',
      render: (log) => (
        <span className="text-xs whitespace-nowrap text-slate-500">
          {log.created_at ? `${fmtDate(log.created_at)} ${fmtTime(log.created_at)}` : '—'}
        </span>
      ),
    },
    {
      key: 'action',
      header: '액션',
      render: (log) => <ActionBadge action={log.action} />,
    },
    {
      key: 'target',
      header: '대상',
      render: (log) => (
        <span className="text-sm text-slate-600">
          {log.target_type
            ? (TARGET_TYPE_LABELS[log.target_type] ?? log.target_type)
            : '—'}
          {log.target_id && (
            <code className="ml-1.5 rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] text-slate-400">
              {log.target_id}
            </code>
          )}
        </span>
      ),
    },
    {
      key: 'actor',
      header: '수행자',
      render: (log) => (
        <span className="text-sm font-medium text-slate-700">
          {log.actor_name ?? log.actor_id ?? '—'}
        </span>
      ),
    },
  ]

  if (isError) {
    return (
      <EmptyState
        icon={<ClipboardText size={36} />}
        title="감사 로그를 불러오지 못했습니다"
        description="감사 로그 API(GET /audit-logs)가 아직 배포되지 않았거나 서버에 연결할 수 없습니다."
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

  return (
    <div className="space-y-3">
      <FilterBar>
        <FilterSelect
          label="액션 유형"
          value={action}
          options={Object.entries(ACTION_SPECS).map(([value, spec]) => ({
            value,
            label: spec.label,
          }))}
          onChange={(v) => {
            setAction(v)
            resetPage()
          }}
        />
        <label className="flex items-center gap-1.5">
          <span className="shrink-0 text-xs font-medium text-slate-500">기간</span>
          <input
            type="date"
            value={dateFrom}
            max={dateTo || undefined}
            onChange={(e) => {
              setDateFrom(e.target.value)
              resetPage()
            }}
            className="h-9 rounded-lg border border-slate-200 bg-white px-2 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
            aria-label="시작일"
          />
          <span className="text-xs text-slate-400">~</span>
          <input
            type="date"
            value={dateTo}
            min={dateFrom || undefined}
            onChange={(e) => {
              setDateTo(e.target.value)
              resetPage()
            }}
            className="h-9 rounded-lg border border-slate-200 bg-white px-2 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
            aria-label="종료일"
          />
        </label>
        {(action || dateFrom || dateTo) && (
          <button
            type="button"
            onClick={() => {
              setAction('')
              setDateFrom('')
              setDateTo('')
              resetPage()
            }}
            className="text-xs font-medium text-slate-400 hover:text-slate-600"
          >
            필터 초기화
          </button>
        )}
      </FilterBar>

      <DataTable
        columns={columns}
        rows={data?.items ?? []}
        rowKey={(log) => log.log_id}
        isLoading={isLoading}
        emptyTitle="감사 로그가 없습니다"
        emptyDescription="조건에 맞는 감사 이벤트가 없습니다. 필터를 조정해 보세요."
      />

      {(data?.total ?? 0) > PAGE_SIZE && (
        <Pagination
          total={data?.total ?? 0}
          page={page}
          pageSize={PAGE_SIZE}
          onChange={setPage}
        />
      )}
    </div>
  )
}
