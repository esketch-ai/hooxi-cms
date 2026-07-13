// SCR-14 감사 로그 탭 (ADMIN 전용) — tb_audit_log 조회 (GAN A10)
// 필터(액션 유형·기간) + 테이블(시각·액션 배지·대상·수행자) + 페이지네이션
import { useState } from 'react'
import { ClipboardText } from '@phosphor-icons/react'
import { DataTable, type Column } from '../../components/DataTable'
import { EmptyState } from '../../components/EmptyState'
import { FilterBar, FilterSelect } from '../../components/FilterBar'
import { Pagination } from '../../components/Pagination'
import { fmtServerDate, fmtServerTime } from '../../lib/format'
import { useAuditLogs, type AuditLogItem } from './api'

const PAGE_SIZE = 20

// 액션 한국어 라벨 + 배지 톤
const ACTION_SPECS: Record<string, { label: string; cls: string }> = {
  REVEAL_AUTH: { label: '인증정보 열람', cls: 'bg-rose-500/15 text-rose-300 border-rose-400/25' },
  SETTLEMENT_CHANGE: {
    label: '정산 상태 변경',
    cls: 'bg-amber-500/15 text-amber-300 border-amber-400/25',
  },
  REPORT_VIEW: { label: '보고서 열람', cls: 'bg-blue-500/15 text-blue-300 border-blue-400/25' },
  KAKAO_APPROVAL: {
    label: '카카오 연락처 승인',
    cls: 'bg-yellow-500/15 text-yellow-300 border-yellow-400/25',
  },
  CONFIG_CHANGE: { label: '설정 변경', cls: 'bg-purple-500/15 text-purple-300 border-purple-400/25' },
  // 내부 사용자 감사 이력 (SCR-14 계정 관리)
  USER_APPROVE: { label: '가입 승인', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/25' },
  USER_ROLE_CHANGE: { label: '역할 변경', cls: 'bg-indigo-500/15 text-indigo-300 border-indigo-400/25' },
  USER_DEACTIVATE: { label: '계정 비활성화', cls: 'bg-rose-500/15 text-rose-300 border-rose-400/25' },
  USER_PIN_RESET: { label: 'PIN 초기화', cls: 'bg-white/10 text-ash border-hairline' },
  USER_CREATE: { label: '계정 생성', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/25' },
  USER_UPDATE: { label: '계정 정보 수정', cls: 'bg-white/10 text-ash border-hairline' },
  USER_REACTIVATE: { label: '계정 재활성화', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/25' },
  INTEGRATION_CHANGE: { label: '연동 설정 변경', cls: 'bg-purple-500/15 text-purple-300 border-purple-400/25' },
  INTEGRATION_REVEAL: { label: '연동 정보 열람', cls: 'bg-rose-500/15 text-rose-300 border-rose-400/25' },
  DOCUMENT_DOWNLOAD: { label: '문서 다운로드', cls: 'bg-sky-500/15 text-sky-300 border-sky-400/25' },
  BACKUP_CREATE: { label: '수동 백업', cls: 'bg-teal-500/15 text-teal-300 border-teal-400/25' },
  BACKUP_RESTORE: { label: 'DB 복구', cls: 'bg-rose-500/15 text-rose-300 border-rose-400/25' },
  // 업무 이력 감사 (이슈·사업·보고서)
  ISSUE_STATUS_CHANGE: { label: '이슈 상태 변경', cls: 'bg-amber-500/15 text-amber-300 border-amber-400/25' },
  COMMENT_ADD: { label: '코멘트 등록', cls: 'bg-white/10 text-ash border-hairline' },
  PROJECT_CREATE: { label: '사업 등록', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/25' },
  PROJECT_UPDATE: { label: '사업 수정', cls: 'bg-indigo-500/15 text-indigo-300 border-indigo-400/25' },
  PROJECT_DELETE: { label: '사업 삭제', cls: 'bg-rose-500/15 text-rose-300 border-rose-400/25' },
  REPORT_CREATE: { label: '보고서 대상 생성', cls: 'bg-sky-500/15 text-sky-300 border-sky-400/25' },
  REPORT_SEND: { label: '보고서 발송', cls: 'bg-blue-500/15 text-blue-300 border-blue-400/25' },
}

const FALLBACK_SPEC = { label: '', cls: 'bg-white/10 text-ash border-hairline' }

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
  DATABASE: '데이터베이스',
  PROJECT: '감축 사업',
  HISTORY: '활동 이력',
  HISTORY_COMMENT: '이슈 코멘트',
  REPORT_DELIVERY: '보고서',
  INTEGRATION: '연동',
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
        <span className="text-xs whitespace-nowrap text-ash">
          {log.created_at ? `${fmtServerDate(log.created_at)} ${fmtServerTime(log.created_at)}` : '—'}
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
        <span className="text-sm text-ash">
          {log.target_type
            ? (TARGET_TYPE_LABELS[log.target_type] ?? log.target_type)
            : '—'}
          {log.target_id && (
            <code className="ml-1.5 rounded bg-white/10 px-1 py-0.5 font-mono text-[11px] text-slatey">
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
        <span className="text-sm font-medium text-bone">
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
            className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-white/5"
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
          <span className="shrink-0 text-xs font-medium text-ash">기간</span>
          <input
            type="date"
            value={dateFrom}
            max={dateTo || undefined}
            onChange={(e) => {
              setDateFrom(e.target.value)
              resetPage()
            }}
            className="h-9 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
            aria-label="시작일"
          />
          <span className="text-xs text-slatey">~</span>
          <input
            type="date"
            value={dateTo}
            min={dateFrom || undefined}
            onChange={(e) => {
              setDateTo(e.target.value)
              resetPage()
            }}
            className="h-9 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
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
            className="text-xs font-medium text-slatey hover:text-ash"
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
