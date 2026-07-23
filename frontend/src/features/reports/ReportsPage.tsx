// SCR-12 월간 보고서 발송 관리 — "이번 달, 어느 고객사에 어디까지 됐는가" 한 화면
import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  CaretLeft,
  CaretRight,
  ChatCircleDots,
  CheckCircle,
  CircleNotch,
  DownloadSimple,
  EnvelopeSimple,
  Funnel,
  ListChecks,
  PaperPlaneTilt,
  PaperPlaneRight,
  UploadSimple,
  WarningCircle,
} from '@phosphor-icons/react'
import { useAuth } from '../../app/AuthProvider'
import { PageHeader } from '../../components/PageHeader'
import { DataTable, type Column } from '../../components/DataTable'
import { StatusBadge } from '../../components/StatusBadge'
import { EmptyState } from '../../components/EmptyState'
import { Modal } from '../../components/Modal'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { DropboxPicker } from '../../components/DropboxPicker'
import { FileUploader } from '../../components/FileUploader'
import { useToast } from '../../components/Toast'
import { downloadDocument, downloadErrorMessage } from '../../lib/download'
import { dday, fmtDate, fmtMonth, fmtServerDate } from '../../lib/format'
import type { ReportDelivery } from '../../types'
import {
  useChangeReportStatus,
  useGenerateReports,
  useReports,
  useReportSendPreview,
  useRunReportSendBatch,
  useSendReport,
  useUploadReportFile,
} from './api'
import { ReportDrawer } from './ReportDrawer'

const SUMMARY_ORDER: {
  key: 'standby' | 'writing' | 'review' | 'approved' | 'sent' | 'confirmed'
  status: string
  label: string
}[] = [
  { key: 'standby', status: 'STANDBY', label: '미착수' },
  { key: 'writing', status: 'WRITING', label: '작성중' },
  { key: 'review', status: 'REVIEW', label: '내부검토' },
  { key: 'approved', status: 'APPROVED', label: '발송승인' },
  { key: 'sent', status: 'SENT', label: '발송완료' },
  { key: 'confirmed', status: 'CONFIRMED', label: '고객확인' },
]

export function ReportsPage() {
  const { showToast } = useToast()
  const { user: me } = useAuth()
  const isAdmin = me?.role === 'ADMIN'
  const [period, setPeriod] = useState(() => fmtMonth(new Date()))
  const { data, isLoading, isError, refetch } = useReports(period)
  const reports = useMemo(() => data?.items ?? [], [data])

  // 상태 필터 — URL ?status= 단일 원천 (현황판 위젯 클릭 진입·공유 링크 지원)
  const [searchParams, setSearchParams] = useSearchParams()
  const statusFilter = searchParams.get('status')
  const setStatusFilter = (status: string | null) =>
    setSearchParams(status ? { status } : {}, { replace: true })
  const visibleReports = useMemo(
    () => (statusFilter ? reports.filter((r) => r.status === statusFilter) : reports),
    [reports, statusFilter],
  )

  const [drawerId, setDrawerId] = useState<string | null>(null)
  const [uploadTarget, setUploadTarget] = useState<ReportDelivery | null>(null)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [sendTarget, setSendTarget] = useState<ReportDelivery | null>(null)
  const [dropboxPaths, setDropboxPaths] = useState<string[]>([])
  const [pickerOpen, setPickerOpen] = useState(false)
  const [generateOpen, setGenerateOpen] = useState(false)
  const [batchOpen, setBatchOpen] = useState(false)
  const [confirmTarget, setConfirmTarget] = useState<ReportDelivery | null>(null)
  const [confirmBasis, setConfirmBasis] = useState('유선')

  const upload = useUploadReportFile()
  const send = useSendReport()
  const changeStatus = useChangeReportStatus()
  const generate = useGenerateReports()
  const runBatch = useRunReportSendBatch()
  const batchPreview = useReportSendPreview(batchOpen)

  // 발송 현황 요약 — 서버 summary (schemas.ReportSummary)
  const summary = useMemo(() => {
    const s = data?.summary
    const total = s ? s.target - s.canceled : 0
    const done = (s?.sent ?? 0) + (s?.confirmed ?? 0)
    return {
      total,
      counts:
        s ??
        { target: 0, standby: 0, writing: 0, review: 0, approved: 0, sent: 0, confirmed: 0, canceled: 0 },
      pct: total > 0 ? Math.round((done / total) * 100) : 0,
    }
  }, [data?.summary])

  const movePeriod = (delta: number) => {
    const [y, m] = period.split('-').map(Number)
    setPeriod(fmtMonth(new Date(y, m - 1 + delta, 1)))
  }

  const closeSend = () => {
    setSendTarget(null)
    setDropboxPaths([])
  }

  const handleSend = async () => {
    if (!sendTarget) return
    try {
      await send.mutateAsync({ reportId: sendTarget.report_id, dropboxPaths })
      showToast('보고서가 발송되었습니다. 활동 이력에 자동 기록됩니다.', 'success')
      closeSend()
    } catch {
      showToast('발송에 실패했습니다. 직전 상태가 유지됩니다.', 'danger')
    }
  }

  const handleUpload = async () => {
    if (!uploadTarget || !uploadFile) return
    try {
      await upload.mutateAsync({ reportId: uploadTarget.report_id, file: uploadFile })
      showToast('파일이 업로드되었습니다. (새 버전으로 저장됨)', 'success')
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

  // 발송 승인 — APPROVED 전이. 파일 미확보 시 서버가 409(detail)로 거절 (배치 자동 발송 전제)
  const handleApprove = async (report: ReportDelivery) => {
    try {
      await changeStatus.mutateAsync({ reportId: report.report_id, status: 'APPROVED' })
      showToast('발송 승인되었습니다. 월초 배치에서 자동 발송됩니다.', 'success')
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      showToast(detail ?? '발송 승인에 실패했습니다.', 'danger')
    }
  }

  // ADMIN 수동 배치 — 전월 APPROVED 일괄 발송 (+ 당월 대상 자동 생성, 멱등)
  const handleRunBatch = async () => {
    try {
      const res = await runBatch.mutateAsync()
      showToast(
        `${res.period} 일괄 발송 완료 — 대상 ${res.targets}건 중 성공 ${res.sent}건, 실패 ${res.failed}건`,
        res.failed > 0 ? 'danger' : 'success',
      )
      setBatchOpen(false)
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      showToast(detail ?? '일괄 발송 실행에 실패했습니다.', 'danger')
    }
  }

  // 고객 확인 처리 — 확인 근거(유선·회신메일·대면 등)를 담당자가 선택/입력해 기록.
  // (항상 '유선'으로 하드코딩되던 문제 해소 — confirm_basis는 자유 텍스트 max 20)
  const handleConfirm = async () => {
    if (!confirmTarget) return
    const basis = confirmBasis.trim()
    if (!basis) {
      showToast('확인 근거를 입력하세요.', 'danger')
      return
    }
    try {
      await changeStatus.mutateAsync({
        reportId: confirmTarget.report_id,
        status: 'CONFIRMED',
        confirm_basis: basis,
      })
      showToast(`고객 확인 처리되었습니다. (근거: ${basis})`, 'success')
      setConfirmTarget(null)
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
      className: '!px-2',
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
      className: '!px-2',
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
      className: '!px-2',
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
      className: '!px-2',
      render: (r) =>
        r.status === 'CONFIRMED' ? (
          <span className="text-xs font-semibold text-emerald-400">✓ {fmtServerDate(r.confirmed_at)}</span>
        ) : r.status === 'SENT' ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              setConfirmBasis('유선')
              setConfirmTarget(r)
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
      stickyRight: true,
      render: (r) => {
        const canUpload = !['SENT', 'CONFIRMED', 'CANCELED', 'MERGED'].includes(r.status)
        const canApprove = ['WRITING', 'REVIEW'].includes(r.status)
        // 발송은 발송승인(APPROVED)에서만 — 승인 게이트를 강제하고, '발송 승인'과
        // '발송' 버튼이 한 행에 겹치지 않게 한다. 발송 성공 시 SENT로 전이돼 월초
        // 배치(APPROVED 대상)와 중복되지 않는다.
        const canSend = r.status === 'APPROVED'
        return (
          <div className="flex justify-end gap-1">
            {canApprove && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  void handleApprove(r)
                }}
                className="hidden items-center gap-1 rounded-full border border-sky-400/25 bg-sky-500/15 px-2.5 py-1.5 text-xs font-semibold text-sky-700 hover:bg-sky-500/25 sm:flex dark:text-sky-300"
                title="발송 승인 — 월초 배치 자동 발송 대상으로 지정"
              >
                <CheckCircle size={13} weight="fill" />
                발송 승인
              </button>
            )}
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
          <>
            <Link
              to="/reports/segments"
              className="hidden items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate sm:flex"
              title="조건으로 고객사를 묶어 자료를 일괄 발송"
            >
              <Funnel size={16} />
              세그먼트 발송
            </Link>
            <button
              type="button"
              onClick={() => setGenerateOpen(true)}
              className="hidden items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate sm:flex"
              title="이번 달 발송 대상(보고서) 생성 — 구독 활성 고객사 기준"
            >
              <ListChecks size={16} />
              대상 생성
            </button>
            {isAdmin && (
              <button
                type="button"
                onClick={() => setBatchOpen(true)}
                className="hidden items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate sm:flex"
                title="월초 배치 수동 실행 — 전월 발송승인 건 일괄 발송"
              >
                <PaperPlaneTilt size={16} />
                전월 승인분 일괄 발송
              </button>
            )}
          </>
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
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => setStatusFilter(null)}
              className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                !statusFilter
                  ? 'border-transparent bg-primary text-on-primary'
                  : 'border-hairline text-ash hover:bg-elevate'
              }`}
            >
              대상 <b>{summary.total}</b>개사
            </button>
            {SUMMARY_ORDER.map(({ key, status, label }) => (
              <button
                key={key}
                type="button"
                onClick={() => setStatusFilter(statusFilter === status ? null : status)}
                title={`${label} 건만 보기`}
                className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                  statusFilter === status
                    ? 'border-transparent bg-primary text-on-primary'
                    : 'border-hairline text-ash hover:bg-elevate'
                }`}
              >
                {label} <b>{summary.counts[key] ?? 0}</b>
              </button>
            ))}
            {(summary.counts.canceled ?? 0) > 0 && (
              <button
                type="button"
                onClick={() => setStatusFilter(statusFilter === 'CANCELED' ? null : 'CANCELED')}
                title="취소 건만 보기"
                className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                  statusFilter === 'CANCELED'
                    ? 'border-transparent bg-primary text-on-primary'
                    : 'border-hairline text-slatey hover:bg-elevate'
                }`}
              >
                취소 <b>{summary.counts.canceled}</b>
              </button>
            )}
          </div>
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
          rows={visibleReports}
          rowKey={(r) => r.report_id}
          isLoading={isLoading}
          onRowClick={(r) => setDrawerId(r.report_id)}
          rowClassName={(r) =>
            r.status === 'CANCELED' || r.status === 'MERGED' ? 'opacity-50' : ''
          }
          emptyTitle={
            statusFilter && reports.length > 0
              ? '해당 상태의 보고서가 없습니다'
              : `${period} 발송 대상이 없습니다`
          }
          emptyDescription={
            statusFilter && reports.length > 0
              ? '위 상태 칩을 다시 누르면 전체 목록으로 돌아갑니다.'
              : '[대상 생성]으로 보고서 수신 설정 고객사의 당월 대상을 만들 수 있습니다.'
          }
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
            <span className="mt-3 flex items-center gap-2 border-t border-hairline pt-3">
              <button
                type="button"
                onClick={() => setPickerOpen(true)}
                className="rounded-full border border-hairline px-3 py-1.5 text-xs font-medium text-bone hover:bg-elevate"
              >
                Dropbox에서 첨부 선택
              </button>
              {dropboxPaths.length > 0 && (
                <span className="text-xs text-slatey">{dropboxPaths.length}개 추가 첨부</span>
              )}
            </span>
          </>
        }
        confirmLabel="발송"
        danger
        loading={send.isPending}
        onConfirm={handleSend}
        onCancel={closeSend}
      />

      {/* Dropbox 라이브 브라우즈 파일 피커 (발송 첨부 선택) */}
      <DropboxPicker
        open={pickerOpen}
        endpoint={sendTarget ? `/clients/${sendTarget.client_id}/dropbox/tree` : null}
        initialSelected={dropboxPaths}
        onClose={() => setPickerOpen(false)}
        onConfirm={(paths) => {
          setDropboxPaths(paths)
          setPickerOpen(false)
        }}
      />

      {/* 고객 확인 처리 — 확인 근거 입력 (유선/회신메일/대면 등) */}
      <Modal
        open={!!confirmTarget}
        onClose={() => (changeStatus.isPending ? undefined : setConfirmTarget(null))}
        title="고객 확인 처리"
        size="sm"
        footer={
          <>
            <button
              type="button"
              onClick={() => setConfirmTarget(null)}
              disabled={changeStatus.isPending}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate disabled:opacity-60"
            >
              취소
            </button>
            <button
              type="button"
              onClick={() => void handleConfirm()}
              disabled={changeStatus.isPending || !confirmBasis.trim()}
              className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-60"
            >
              {changeStatus.isPending && <CircleNotch size={14} className="animate-spin" />}
              확인 처리
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <p className="text-sm text-ash">
            <b className="text-bone">{confirmTarget?.client_name}</b> · {period}{' '}
            {confirmTarget?.report_type} 건을 <b className="text-bone">고객확인(CONFIRMED)</b>{' '}
            상태로 기록합니다.
          </p>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-ash">확인 근거</span>
            <input
              type="text"
              list="confirm-basis-suggestions"
              value={confirmBasis}
              maxLength={20}
              onChange={(e) => setConfirmBasis(e.target.value)}
              placeholder="예: 유선 / 회신메일 / 대면 / 열람"
              className="w-full rounded-lg border border-hairline bg-graphite px-3 py-2 text-sm text-bone focus:border-white/30 focus:outline-none"
            />
            <datalist id="confirm-basis-suggestions">
              <option value="유선" />
              <option value="회신메일" />
              <option value="대면" />
              <option value="열람" />
            </datalist>
          </label>
          <p className="text-xs text-slatey">
            실제 확인 방식을 입력하세요. 활동 이력·발송 기록에 이 근거가 함께 남습니다.
          </p>
        </div>
      </Modal>

      {/* 월초 배치 수동 실행 — 발송 전 미리보기 확인 (ADMIN) */}
      <Modal
        open={batchOpen}
        onClose={() => (runBatch.isPending ? undefined : setBatchOpen(false))}
        title="전월 승인분 일괄 발송 — 발송 전 확인"
        size="xl"
        footer={
          <>
            <button
              type="button"
              onClick={() => setBatchOpen(false)}
              disabled={runBatch.isPending}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate disabled:opacity-60"
            >
              취소
            </button>
            <button
              type="button"
              onClick={handleRunBatch}
              disabled={
                runBatch.isPending ||
                batchPreview.isLoading ||
                !batchPreview.data ||
                batchPreview.data.total === 0
              }
              className="flex items-center gap-1.5 rounded-full bg-rose-500/90 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-500 disabled:opacity-60"
            >
              {runBatch.isPending && <CircleNotch size={14} className="animate-spin" />}
              {batchPreview.data && batchPreview.data.ready_count > 0
                ? `${batchPreview.data.ready_count}건 발송`
                : '발송'}
            </button>
          </>
        }
      >
        {batchPreview.isLoading ? (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-ash">
            <CircleNotch size={18} className="animate-spin" />
            발송 대상을 확인하는 중…
          </div>
        ) : batchPreview.isError ? (
          <div className="py-8 text-center text-sm text-rose-300">
            발송 대상을 불러오지 못했습니다. 잠시 후 다시 시도하세요.
          </div>
        ) : batchPreview.data && batchPreview.data.total > 0 ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-bone">
                <b>{batchPreview.data.period}</b> 발송승인(APPROVED){' '}
                <b>{batchPreview.data.total}</b>건
              </span>
              <span className="rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-xs font-medium text-emerald-300">
                발송 가능 {batchPreview.data.ready_count}
              </span>
              {batchPreview.data.blocked_count > 0 && (
                <span className="rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-medium text-amber-300">
                  확인 필요 {batchPreview.data.blocked_count}
                </span>
              )}
            </div>

            <div className="max-h-[46vh] overflow-auto rounded-2xl border border-hairline">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-elevate text-xs text-ash">
                  <tr>
                    <th className="px-3 py-2 font-medium">고객사</th>
                    <th className="px-3 py-2 font-medium">보고서</th>
                    <th className="px-3 py-2 font-medium">첨부파일명</th>
                    <th className="px-3 py-2 text-center font-medium">수신자</th>
                    <th className="px-3 py-2 font-medium">상태</th>
                  </tr>
                </thead>
                <tbody>
                  {batchPreview.data.items.map((it) => (
                    <tr key={it.report_id} className="border-t border-hairline align-top">
                      <td className="px-3 py-2 text-bone">{it.client_name ?? '—'}</td>
                      <td className="px-3 py-2 text-ash">
                        {it.period} · {it.report_type}
                      </td>
                      <td className="px-3 py-2">
                        {it.filename ? (
                          <span className="break-all font-mono text-xs text-bone">
                            {it.filename}
                          </span>
                        ) : (
                          <span className="text-xs text-ash">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-center text-ash">{it.recipients}</td>
                      <td className="px-3 py-2">
                        {it.ready ? (
                          <span className="inline-flex items-center gap-1 text-xs text-emerald-300">
                            <CheckCircle size={14} weight="fill" />
                            발송 가능
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs text-amber-300">
                            <WarningCircle size={14} weight="fill" />
                            {it.issue ?? '확인 필요'}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="text-xs text-ash">
              첨부파일명을 확인하세요(첨부는 발송 시점에 최종 확인됩니다). 건별로 실제
              이메일·알림톡이 발송되며 되돌릴 수 없습니다.
              {batchPreview.data.blocked_count > 0 && (
                <>
                  {' '}
                  <b className="text-amber-300">확인 필요</b> 건은 발송 시 실패로 격리되어 상태가
                  유지됩니다(다른 건은 정상 발송).
                </>
              )}{' '}
              당월 발송 대상 자동 생성이 함께 수행됩니다.
            </p>
          </div>
        ) : (
          <div className="py-8 text-center text-sm text-ash">
            {batchPreview.data?.period ?? ''} 발송할 <b>발송승인(APPROVED)</b> 보고서가 없습니다.
          </div>
        )}
      </Modal>

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
