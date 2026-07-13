// SCR-12 월간 보고서 발송 관리 — "이번 달, 어느 고객사에 어디까지 됐는가" 한 화면
import { useMemo, useState } from 'react'
import {
  CaretLeft,
  CaretRight,
  ChatCircleDots,
  CircleNotch,
  DownloadSimple,
  EnvelopeSimple,
  ListChecks,
  PaperPlaneTilt,
  PaperPlaneRight,
  UploadSimple,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { DataTable, type Column } from '../../components/DataTable'
import { StatusBadge } from '../../components/StatusBadge'
import { EmptyState } from '../../components/EmptyState'
import { Modal } from '../../components/Modal'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { FileUploader } from '../../components/FileUploader'
import { useToast } from '../../components/Toast'
import { downloadDocument, downloadErrorMessage } from '../../lib/download'
import { dday, fmtDate, fmtMonth, fmtServerDate } from '../../lib/format'
import type { ReportDelivery } from '../../types'
import {
  useChangeReportStatus,
  useGenerateReports,
  useReports,
  useSendReport,
  useUploadReportFile,
} from './api'
import { ReportDrawer } from './ReportDrawer'

const SUMMARY_ORDER: { key: 'standby' | 'writing' | 'review' | 'sent' | 'confirmed'; label: string }[] = [
  { key: 'standby', label: '미착수' },
  { key: 'writing', label: '작성중' },
  { key: 'review', label: '검토' },
  { key: 'sent', label: '발송완료' },
  { key: 'confirmed', label: '고객확인' },
]

export function ReportsPage() {
  const { showToast } = useToast()
  const [period, setPeriod] = useState(() => fmtMonth(new Date()))
  const { data, isLoading, isError, refetch } = useReports(period)
  const reports = useMemo(() => data?.items ?? [], [data])

  const [drawerId, setDrawerId] = useState<string | null>(null)
  const [uploadTarget, setUploadTarget] = useState<ReportDelivery | null>(null)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [sendTarget, setSendTarget] = useState<ReportDelivery | null>(null)
  const [generateOpen, setGenerateOpen] = useState(false)

  const upload = useUploadReportFile()
  const send = useSendReport()
  const changeStatus = useChangeReportStatus()
  const generate = useGenerateReports()

  // 발송 현황 요약 — 서버 summary (schemas.ReportSummary)
  const summary = useMemo(() => {
    const s = data?.summary
    const total = s ? s.target - s.canceled : 0
    const done = (s?.sent ?? 0) + (s?.confirmed ?? 0)
    return {
      total,
      counts: s ?? { target: 0, standby: 0, writing: 0, review: 0, sent: 0, confirmed: 0, canceled: 0 },
      pct: total > 0 ? Math.round((done / total) * 100) : 0,
    }
  }, [data?.summary])

  const movePeriod = (delta: number) => {
    const [y, m] = period.split('-').map(Number)
    setPeriod(fmtMonth(new Date(y, m - 1 + delta, 1)))
  }

  const handleSend = async () => {
    if (!sendTarget) return
    try {
      await send.mutateAsync(sendTarget.report_id)
      showToast('보고서가 발송되었습니다. 활동 이력에 자동 기록됩니다.', 'success')
      setSendTarget(null)
    } catch {
      showToast('발송에 실패했습니다. 직전 상태가 유지됩니다.', 'danger')
    }
  }

  const handleUpload = async () => {
    if (!uploadTarget || !uploadFile) return
    try {
      await upload.mutateAsync({ reportId: uploadTarget.report_id, file: uploadFile })
      showToast('파일이 업로드되었습니다. (버전 적재)', 'success')
      setUploadTarget(null)
      setUploadFile(null)
    } catch {
      showToast('업로드에 실패했습니다.', 'danger')
    }
  }

  const handleGenerate = async () => {
    try {
      await generate.mutateAsync(period)
      showToast(`${period} 발송 대상이 생성되었습니다.`, 'success')
      setGenerateOpen(false)
    } catch {
      showToast('대상 생성에 실패했습니다.', 'danger')
    }
  }

  const handleConfirm = async (report: ReportDelivery) => {
    try {
      await changeStatus.mutateAsync({
        reportId: report.report_id,
        status: 'CONFIRMED',
        confirm_basis: '유선',
      })
      showToast('고객 확인 처리되었습니다.', 'success')
    } catch {
      showToast('고객 확인 처리에 실패했습니다.', 'danger')
    }
  }

  // 다운로드 실패(404/503 등) 시 에러 토스트 (L-3)
  const handleDownload = async (docId: string, title?: string) => {
    try {
      await downloadDocument(docId, title)
    } catch (err) {
      showToast(downloadErrorMessage(err), 'danger')
    }
  }

  const columns: Column<ReportDelivery>[] = [
    {
      key: 'client',
      header: '고객사',
      render: (r) => (
        <span className="font-semibold text-bone">{r.client_name ?? r.client_id}</span>
      ),
    },
    {
      key: 'type',
      header: '보고서 유형',
      render: (r) => <span className="text-ash">{r.report_type}</span>,
    },
    {
      key: 'manager',
      header: '담당자',
      render: (r) => <span className="text-ash">{r.manager_name ?? '—'}</span>,
    },
    {
      key: 'status',
      header: '상태',
      render: (r) => <StatusBadge domain="report" value={r.status} />,
    },
    {
      key: 'due',
      header: '마감일 / 발송일',
      render: (r) => {
        const d = r.status === 'SENT' || r.status === 'CONFIRMED' ? null : dday(r.due_date)
        return (
          <div className="text-xs">
            <span className="text-ash">
              {r.sent_at ? fmtServerDate(r.sent_at) : fmtDate(r.due_date)}
            </span>
            {d && (
              <span
                className={`ml-1.5 font-bold ${
                  d.overdue ? 'text-rose-400' : d.imminent ? 'text-rose-400' : 'text-slatey'
                }`}
              >
                {d.label}
              </span>
            )}
          </div>
        )
      },
    },
    {
      key: 'file',
      header: '파일',
      render: (r) =>
        r.latest_doc ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              void handleDownload(r.latest_doc!.doc_id, r.latest_doc!.title)
            }}
            className="inline-flex items-center gap-1 text-xs font-medium text-ash hover:underline"
          >
            <DownloadSimple size={13} />
            v{r.latest_doc.version}
          </button>
        ) : r.doc_id ? (
          <span className="text-xs text-ash">있음</span>
        ) : (
          <span className="text-xs text-slatey">없음</span>
        ),
    },
    {
      key: 'channel',
      header: '채널',
      render: (r) => (
        <span className="flex items-center gap-1 text-slatey">
          {(r.sent_channel === 'EMAIL' || r.sent_channel === 'BOTH') && (
            <EnvelopeSimple size={15} className="text-ash" />
          )}
          {(r.sent_channel === 'KAKAO' || r.sent_channel === 'BOTH') && (
            <ChatCircleDots size={15} className="text-amber-400" />
          )}
          {!r.sent_channel && <span className="text-xs text-slatey">—</span>}
        </span>
      ),
    },
    {
      key: 'confirmed',
      header: '고객 확인',
      render: (r) =>
        r.status === 'CONFIRMED' ? (
          <span className="text-xs font-semibold text-emerald-400">✓ {fmtServerDate(r.confirmed_at)}</span>
        ) : r.status === 'SENT' ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              handleConfirm(r)
            }}
            className="rounded-full border border-hairline px-2 py-1 text-xs font-medium text-bone hover:bg-elevate"
          >
            확인 처리
          </button>
        ) : (
          <span className="text-xs text-slatey">—</span>
        ),
    },
    {
      key: 'actions',
      header: '관리',
      className: 'text-right',
      render: (r) => {
        const canUpload = !['SENT', 'CONFIRMED', 'CANCELED', 'MERGED'].includes(r.status)
        const canSend =
          !!(r.doc_id || r.latest_doc) && ['WRITING', 'REVIEW', 'STANDBY'].includes(r.status)
        return (
          <div className="flex justify-end gap-1">
            {canUpload && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  setUploadTarget(r)
                  setUploadFile(null)
                }}
                className="hidden rounded-lg p-1.5 text-smoke hover:bg-elevate hover:text-bone sm:block"
                title="파일 업로드"
              >
                <UploadSimple size={16} />
              </button>
            )}
            {canSend && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  setSendTarget(r)
                }}
                className="hidden items-center gap-1 rounded-full bg-primary px-2.5 py-1.5 text-xs font-semibold text-on-primary hover:opacity-90 sm:flex"
                title="발송"
              >
                <PaperPlaneRight size={13} weight="fill" />
                발송
              </button>
            )}
          </div>
        )
      },
    },
  ]

  const selectedDrawer = reports.find((r) => r.report_id === drawerId) ?? null

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="월간 보고서 발송 관리"
        subtitle="담당자 작성 파일 업로드 + 발송 추적 — 부서 전체 공동 관리"
        actions={
          <button
            type="button"
            onClick={() => setGenerateOpen(true)}
            className="hidden items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate sm:flex"
          >
            <ListChecks size={16} />
            대상 생성
          </button>
        }
      />

      {/* 월 선택기 + 발송 현황 요약 바 */}
      <div className="rounded-3xl border border-hairline bg-graphite p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => movePeriod(-1)}
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-hairline text-ash hover:bg-elevate"
              aria-label="이전 달"
            >
              <CaretLeft size={14} />
            </button>
            <span className="w-24 text-center font-mono text-sm font-bold text-bone">
              {period}
            </span>
            <button
              type="button"
              onClick={() => movePeriod(1)}
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-hairline text-ash hover:bg-elevate"
              aria-label="다음 달"
            >
              <CaretRight size={14} />
            </button>
          </div>
          <p className="text-sm text-ash">
            대상 <b className="text-bone">{summary.total}</b>개사
            <span className="mx-2 text-slatey">|</span>
            {SUMMARY_ORDER.map(({ key, label }, i) => (
              <span key={key}>
                {i > 0 && <span className="mx-1 text-slatey">·</span>}
                {label} <b className="text-bone">{summary.counts[key] ?? 0}</b>
              </span>
            ))}
          </p>
          <div className="ml-auto flex min-w-[160px] items-center gap-2">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-elevate">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all"
                style={{ width: `${summary.pct}%` }}
              />
            </div>
            <span className="text-xs font-semibold text-ash">{summary.pct}%</span>
          </div>
        </div>
      </div>

      {isError ? (
        <EmptyState
          icon={<PaperPlaneTilt size={36} />}
          title="발송 현황을 불러오지 못했습니다"
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
          rows={reports}
          rowKey={(r) => r.report_id}
          isLoading={isLoading}
          onRowClick={(r) => setDrawerId(r.report_id)}
          rowClassName={(r) =>
            r.status === 'CANCELED' || r.status === 'MERGED' ? 'opacity-50' : ''
          }
          emptyTitle={`${period} 발송 대상이 없습니다`}
          emptyDescription="[대상 생성]으로 보고서 수신 설정 고객사의 당월 대상을 만들 수 있습니다."
          renderCard={(r) => (
            <button
              type="button"
              onClick={() => setDrawerId(r.report_id)}
              className="w-full text-left"
            >
              <div className="flex items-center gap-2">
                <p className="min-w-0 flex-1 truncate font-semibold text-bone">
                  {r.client_name ?? r.client_id}
                </p>
                <StatusBadge domain="report" value={r.status} />
              </div>
              <p className="mt-1 text-xs text-slatey">
                {r.report_type} · {r.manager_name ?? '—'} · 마감 {fmtDate(r.due_date)}
              </p>
            </button>
          )}
        />
      )}

      {/* 행 상세 Drawer */}
      <ReportDrawer report={selectedDrawer} onClose={() => setDrawerId(null)} />

      {/* 파일 업로드 Modal */}
      <Modal
        open={!!uploadTarget}
        onClose={() => setUploadTarget(null)}
        title={`파일 업로드 — ${uploadTarget?.client_name ?? ''} (${period})`}
        size="md"
        footer={
          <>
            <button
              type="button"
              onClick={() => setUploadTarget(null)}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
            >
              취소
            </button>
            <button
              type="button"
              onClick={handleUpload}
              disabled={!uploadFile || upload.isPending}
              className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-60"
            >
              {upload.isPending && <CircleNotch size={14} className="animate-spin" />}
              업로드
            </button>
          </>
        }
      >
        <div className="space-y-2">
          <FileUploader
            file={uploadFile}
            onChange={setUploadFile}
            accept=".pdf,.docx,.xlsx,.pptx,.hwp,.hwpx"
          />
          <p className="text-xs text-slatey">
            업로드 시 새 버전으로 적재되며, 발송 시점의 파일 버전이 고정 기록됩니다.
          </p>
        </div>
      </Modal>

      {/* 발송 확인 다이얼로그 */}
      <ConfirmDialog
        open={!!sendTarget}
        title="보고서 발송"
        message={
          <>
            <b>{sendTarget?.client_name}</b>에 {period} {sendTarget?.report_type}을(를)
            발송합니다.
            <br />
            회사 대표 지메일 계정으로 이메일(파일 첨부)이 발송되고, 카카오 채널 연동
            고객사는 알림톡 안내가 병행됩니다.
          </>
        }
        confirmLabel="발송"
        danger
        loading={send.isPending}
        onConfirm={handleSend}
        onCancel={() => setSendTarget(null)}
      />

      {/* 대상 생성 확인 */}
      <ConfirmDialog
        open={generateOpen}
        title="발송 대상 생성"
        message={
          <>
            {period} 기준, 보고서 수신 설정(report_yn=Y)이 켜진 고객사의 발송 대상을
            생성합니다. 이미 생성된 대상은 중복 생성되지 않습니다.
          </>
        }
        confirmLabel="생성"
        loading={generate.isPending}
        onConfirm={handleGenerate}
        onCancel={() => setGenerateOpen(false)}
      />
    </div>
  )
}
