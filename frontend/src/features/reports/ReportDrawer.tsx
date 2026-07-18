// SCR-12 행 Drawer — 버전 히스토리 · 발송 기록 (append-only send_log)
import { useState } from 'react'
import { DownloadSimple, PushPin } from '@phosphor-icons/react'
import { Drawer } from '../../components/Drawer'
import { StatusBadge } from '../../components/StatusBadge'
import { Skeleton } from '../../components/Skeleton'
import { DocumentPreviewModal } from '../../components/DocumentPreviewModal'
import { useToast } from '../../components/Toast'
import { downloadDocument, downloadErrorMessage, previewKind } from '../../lib/download'
import { fmtDate, fmtServerDate, fmtServerDateTime } from '../../lib/format'
import type { Document, ReportDelivery } from '../../types'
import { usePinReportDocument, useReportDetail } from './api'

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
  const pinDocument = usePinReportDocument()
  // 버전 제목 클릭 → 미리보기(PDF/이미지만) — Drawer 위에 미리보기 모달 중첩(DOM 후순위로 최상단)
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null)

  // 다운로드 실패(404/503 등) 시 에러 토스트 (L-3)
  const handleDownload = async (docId: string, title?: string) => {
    try {
      await downloadDocument(docId, title)
    } catch (err) {
      showToast(downloadErrorMessage(err), 'danger')
    }
  }

  // 고정본 지정/해제 (R2-B4) — 409(종결 상태)·422(타 보고서 문서) detail 그대로 노출
  const handlePin = async (reportId: string, docId: string | null) => {
    try {
      await pinDocument.mutateAsync({ reportId, docId })
      showToast(docId ? '고정본으로 지정했습니다.' : '고정을 해제했습니다 (최신본 발송).', 'success')
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      showToast(detail ?? '고정본 변경에 실패했습니다.', 'danger')
    }
  }

  if (!report) return null
  const merged = { ...report, ...(detail ?? {}) }
  const versions = merged.documents ?? (merged.latest_doc ? [merged.latest_doc] : [])
  const sendLogs = merged.send_logs ?? []
  // 발송 파일 선정은 발송 전 단계에서만 의미 — 종결 상태에서는 고정 버튼 숨김(백엔드 409 규칙과 일치)
  const canPin = !['SENT', 'CONFIRMED', 'CANCELED'].includes(merged.status)

  return (
    <>
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
          <dl className="grid grid-cols-2 gap-2 rounded-2xl bg-elevate p-3 text-sm">
            <div>
              <dt className="text-xs text-slatey">보고서 유형</dt>
              <dd className="font-medium text-bone">{merged.report_type}</dd>
            </div>
            <div>
              <dt className="text-xs text-slatey">담당자</dt>
              <dd className="font-medium text-bone">{merged.manager_name ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-slatey">마감일</dt>
              <dd className="font-medium text-bone">{fmtDate(merged.due_date)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slatey">발송일 / 채널</dt>
              <dd className="font-medium text-bone">
                {fmtServerDate(merged.sent_at)}{' '}
                {merged.sent_channel
                  ? `· ${CHANNEL_LABELS[merged.sent_channel] ?? merged.sent_channel}`
                  : ''}
              </dd>
            </div>
            {merged.confirmed_at && (
              <div className="col-span-2">
                <dt className="text-xs text-slatey">고객 확인</dt>
                <dd className="font-medium text-emerald-400">
                  {fmtServerDateTime(merged.confirmed_at)}
                  {merged.confirm_basis ? ` (${merged.confirm_basis})` : ''}
                </dd>
              </div>
            )}
            {merged.canceled_reason && (
              <div className="col-span-2">
                <dt className="text-xs text-slatey">취소·복원 사유</dt>
                <dd className="text-ash">{merged.canceled_reason}</dd>
              </div>
            )}
          </dl>

          {isLoading && (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-4/5" />
            </div>
          )}

          {/* 버전 히스토리 — 발송 파일 선정: 고정본 우선, 없으면 최신본 (R2-B4) */}
          <section>
            <h3 className="mb-1 text-xs font-semibold text-slatey">
              버전 히스토리 (파일 업로드 이력)
            </h3>
            <p className="mb-2 text-[11px] text-slatey">
              발송 시 고정본을 우선 사용하고, 고정본이 없으면 최신 버전을 발송합니다.
            </p>
            {versions.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-hairline py-4 text-center text-xs text-slatey">
                업로드된 파일이 없습니다
              </p>
            ) : (
              <ul className="divide-y divide-hairline rounded-2xl border border-hairline">
                {versions.map((d) => {
                  const isPinned = merged.pinned_doc_id === d.doc_id
                  return (
                    <li key={d.doc_id} className="flex items-center gap-3 px-3 py-2.5">
                      <span className="rounded bg-elevate-strong px-1.5 py-0.5 font-mono text-[11px] font-semibold text-ash">
                        v{d.version}
                      </span>
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
                        <p className="text-[11px] text-slatey">
                          {d.uploaded_by_name ?? '—'} · {fmtServerDateTime(d.created_at)}
                        </p>
                      </div>
                      {isPinned && (
                        <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-emerald-400/25 bg-emerald-500/15 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300">
                          <PushPin size={11} weight="fill" />
                          고정됨
                        </span>
                      )}
                      {canPin &&
                        (isPinned ? (
                          <button
                            type="button"
                            onClick={() => void handlePin(merged.report_id, null)}
                            disabled={pinDocument.isPending}
                            className="shrink-0 rounded-full border border-hairline px-2.5 py-1 text-[11px] font-medium text-bone hover:bg-elevate disabled:opacity-50"
                            title="고정 해제 (최신본 발송으로 복귀)"
                          >
                            해제
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => void handlePin(merged.report_id, d.doc_id)}
                            disabled={pinDocument.isPending}
                            className="flex shrink-0 items-center gap-1 rounded-full border border-hairline px-2.5 py-1 text-[11px] font-medium text-bone hover:bg-elevate disabled:opacity-50"
                            title="이 버전을 발송 고정본으로 지정"
                          >
                            <PushPin size={11} />
                            고정
                          </button>
                        ))}
                      <button
                        type="button"
                        onClick={() => void handleDownload(d.doc_id, d.title)}
                        className="rounded-lg p-1.5 text-smoke hover:bg-elevate hover:text-bone"
                        title="다운로드"
                      >
                        <DownloadSimple size={16} />
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>

          {/* 발송 기록 (회차별) */}
          <section>
            <h3 className="mb-2 text-xs font-semibold text-slatey">발송 기록 (회차별)</h3>
            {sendLogs.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-hairline py-4 text-center text-xs text-slatey">
                발송 기록이 없습니다
              </p>
            ) : (
              <ul className="divide-y divide-hairline rounded-2xl border border-hairline">
                {sendLogs.map((log) => (
                  <li key={log.send_id} className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="rounded bg-elevate-strong px-1.5 py-0.5 font-mono text-[11px] font-semibold text-ash">
                        #{log.seq}
                      </span>
                      <span className="text-xs font-medium text-ash">
                        {log.channel === 'EMAIL'
                          ? '✉️ 이메일'
                          : log.channel === 'KAKAO'
                            ? '💬 알림톡'
                            : log.channel}
                      </span>
                      <span
                        className={`text-xs font-semibold ${
                          log.result === 'SUCCESS'
                            ? 'text-emerald-400'
                            : log.result === 'FAIL' || log.result === 'BOUNCED'
                              ? 'text-rose-400'
                              : 'text-slatey'
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
                      <span className="ml-auto text-[11px] text-slatey">
                        {fmtServerDateTime(log.created_at)}
                      </span>
                    </div>
                    {log.recipients && (
                      <p className="mt-1 truncate text-[11px] text-slatey">
                        수신: {log.recipients}
                      </p>
                    )}
                    {log.reason && (
                      <p className="mt-0.5 text-[11px] text-slatey">사유: {log.reason}</p>
                    )}
                    <p className="mt-0.5 text-[11px] text-slatey">
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
      {/* Drawer 위 미리보기 — Drawer 패널은 transform 애니메이션이라 내부 fixed가 갇힐 수 있어 형제로 렌더 */}
      <DocumentPreviewModal doc={previewDoc} onClose={() => setPreviewDoc(null)} />
    </>
  )
}
