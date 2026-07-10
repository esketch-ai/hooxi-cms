// SCR-12 행 Drawer — 버전 히스토리 · 발송 기록 (append-only send_log)
import { DownloadSimple } from '@phosphor-icons/react'
import { Drawer } from '../../components/Drawer'
import { StatusBadge } from '../../components/StatusBadge'
import { Skeleton } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { downloadDocument, downloadErrorMessage } from '../../lib/download'
import { fmtDate, fmtServerDate, fmtServerDateTime } from '../../lib/format'
import type { ReportDelivery } from '../../types'
import { useReportDetail } from './api'

interface ReportDrawerProps {
  report: ReportDelivery | null
  onClose: () => void
}

/** 발송 채널 한국어 라벨 (EMAIL/KAKAO/BOTH) */
const CHANNEL_LABELS: Record<string, string> = {
  EMAIL: '이메일',
  KAKAO: '알림톡',
  BOTH: '이메일+알림톡',
}

export function ReportDrawer({ report, onClose }: ReportDrawerProps) {
  const { data: detail, isLoading } = useReportDetail(report?.report_id)
  const { showToast } = useToast()

  // 다운로드 실패(404/503 등) 시 에러 토스트 (L-3)
  const handleDownload = async (docId: string, title?: string) => {
    try {
      await downloadDocument(docId, title)
    } catch (err) {
      showToast(downloadErrorMessage(err), 'danger')
    }
  }

  if (!report) return null
  const merged = { ...report, ...(detail ?? {}) }
  const versions = merged.documents ?? (merged.latest_doc ? [merged.latest_doc] : [])
  const sendLogs = merged.send_logs ?? []

  return (
    <Drawer
      open={!!report}
      onClose={onClose}
      size="lg"
      title={
        <div className="flex items-center gap-2">
          <span className="truncate">
            {merged.client_name ?? '고객사'} · {merged.period}
          </span>
          <StatusBadge domain="report" value={merged.status} />
        </div>
      }
    >
      <div className="space-y-5">
        {/* 요약 */}
        <dl className="grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-3 text-sm">
          <div>
            <dt className="text-xs text-slate-400">보고서 유형</dt>
            <dd className="font-medium text-slate-700">{merged.report_type}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-400">담당자</dt>
            <dd className="font-medium text-slate-700">{merged.manager_name ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-400">마감일</dt>
            <dd className="font-medium text-slate-700">{fmtDate(merged.due_date)}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-400">발송일 / 채널</dt>
            <dd className="font-medium text-slate-700">
              {fmtServerDate(merged.sent_at)}{' '}
              {merged.sent_channel
                ? `· ${CHANNEL_LABELS[merged.sent_channel] ?? merged.sent_channel}`
                : ''}
            </dd>
          </div>
          {merged.confirmed_at && (
            <div className="col-span-2">
              <dt className="text-xs text-slate-400">고객 확인</dt>
              <dd className="font-medium text-emerald-700">
                {fmtServerDateTime(merged.confirmed_at)}
                {merged.confirm_basis ? ` (${merged.confirm_basis})` : ''}
              </dd>
            </div>
          )}
          {merged.canceled_reason && (
            <div className="col-span-2">
              <dt className="text-xs text-slate-400">취소·복원 사유</dt>
              <dd className="text-slate-600">{merged.canceled_reason}</dd>
            </div>
          )}
        </dl>

        {isLoading && (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-4/5" />
          </div>
        )}

        {/* 버전 히스토리 */}
        <section>
          <h3 className="mb-2 text-xs font-semibold text-slate-400">
            버전 히스토리 (파일 업로드 이력)
          </h3>
          {versions.length === 0 ? (
            <p className="rounded-lg border border-dashed border-slate-200 py-4 text-center text-xs text-slate-400">
              업로드된 파일이 없습니다
            </p>
          ) : (
            <ul className="divide-y divide-slate-50 rounded-lg border border-slate-100">
              {versions.map((d) => (
                <li key={d.doc_id} className="flex items-center gap-3 px-3 py-2.5">
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-slate-500">
                    v{d.version}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-700">{d.title}</p>
                    <p className="text-[11px] text-slate-400">
                      {d.uploaded_by_name ?? '—'} · {fmtServerDateTime(d.created_at)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleDownload(d.doc_id, d.title)}
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

        {/* 발송 기록 (회차별) */}
        <section>
          <h3 className="mb-2 text-xs font-semibold text-slate-400">발송 기록 (회차별)</h3>
          {sendLogs.length === 0 ? (
            <p className="rounded-lg border border-dashed border-slate-200 py-4 text-center text-xs text-slate-400">
              발송 기록이 없습니다
            </p>
          ) : (
            <ul className="divide-y divide-slate-50 rounded-lg border border-slate-100">
              {sendLogs.map((log) => (
                <li key={log.send_id} className="px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-slate-500">
                      #{log.seq}
                    </span>
                    <span className="text-xs font-medium text-slate-600">
                      {log.channel === 'EMAIL' ? '✉️ 이메일' : log.channel === 'KAKAO' ? '💬 알림톡' : log.channel}
                    </span>
                    <span
                      className={`text-xs font-semibold ${
                        log.result === 'SUCCESS'
                          ? 'text-emerald-600'
                          : log.result === 'FAIL' || log.result === 'BOUNCED'
                            ? 'text-rose-600'
                            : 'text-slate-400'
                      }`}
                    >
                      {log.result === 'SUCCESS'
                        ? '성공'
                        : log.result === 'FAIL'
                          ? '실패'
                          : log.result === 'BOUNCED'
                            ? '반송'
                            : (log.result ?? '')}
                    </span>
                    <span className="ml-auto text-[11px] text-slate-400">
                      {fmtServerDateTime(log.created_at)}
                    </span>
                  </div>
                  {log.recipients && (
                    <p className="mt-1 truncate text-[11px] text-slate-400">
                      수신: {log.recipients}
                    </p>
                  )}
                  {log.reason && (
                    <p className="mt-0.5 text-[11px] text-slate-400">사유: {log.reason}</p>
                  )}
                  <p className="mt-0.5 text-[11px] text-slate-400">
                    발송자 {log.sent_by_name ?? '—'}
                    {log.confirmed_at ? ` · 고객확인 ${fmtServerDateTime(log.confirmed_at)}` : ''}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </Drawer>
  )
}
