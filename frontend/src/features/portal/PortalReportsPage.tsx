// 포털 P1 — 내 회사 월간 보고서(발송 완료분) 열람·다운로드 (PARTNER 전용)
import { CircleNotch, DownloadSimple, FileText } from '@phosphor-icons/react'
import { api } from '../../lib/api/client'
import { downloadBlob } from '../../lib/download'
import { useToast } from '../../components/Toast'
import { usePortalReports } from './api'
import { useState } from 'react'

const STATUS_LABEL: Record<string, string> = { SENT: '발송완료', CONFIRMED: '확인완료' }

export function PortalReportsPage() {
  const { data: items = [], isLoading } = usePortalReports()
  const { showToast } = useToast()
  const [downloading, setDownloading] = useState<string | null>(null)

  const handleDownload = async (reportId: string, period: string) => {
    setDownloading(reportId)
    try {
      const res = await api.get(`/portal/reports/${reportId}/download`, {
        responseType: 'blob',
        timeout: 60_000,
      })
      downloadBlob(res.data as Blob, `월간보고서_${period}.pdf`)
    } catch {
      showToast('보고서 다운로드에 실패했습니다.', 'danger')
    } finally {
      setDownloading(null)
    }
  }

  if (isLoading) {
    return (
      <p className="flex items-center gap-1.5 text-sm text-ash">
        <CircleNotch size={15} className="animate-spin" />
        불러오는 중…
      </p>
    )
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-lg font-bold text-bone">
          <FileText size={20} weight="fill" />
          월간 보고서
        </h1>
        <p className="mt-0.5 text-sm text-slatey">발송 완료된 보고서를 열람할 수 있습니다.</p>
      </div>

      {items.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-hairline bg-graphite px-6 py-12 text-center text-sm text-slatey">
          발송된 보고서가 없습니다.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-hairline">
          <table className="w-full min-w-[420px] text-left text-sm">
            <thead className="bg-elevate text-xs text-ash">
              <tr>
                <th className="px-3 py-2 font-medium">대상 월</th>
                <th className="px-3 py-2 font-medium">상태</th>
                <th className="px-3 py-2 font-medium">발송일</th>
                <th className="px-3 py-2 text-right font-medium">파일</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {items.map((r) => (
                <tr key={r.report_id}>
                  <td className="px-3 py-2 font-mono text-xs text-bone">{r.period}</td>
                  <td className="px-3 py-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                        r.status === 'CONFIRMED'
                          ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                          : 'bg-sky-500/15 text-sky-700 dark:text-sky-300'
                      }`}
                    >
                      {STATUS_LABEL[r.status] ?? r.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs text-slatey">
                    {r.sent_at ? new Date(r.sent_at).toLocaleDateString('ko-KR') : '—'}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {r.has_file ? (
                      <button
                        type="button"
                        disabled={downloading === r.report_id}
                        onClick={() => handleDownload(r.report_id, r.period)}
                        className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-3 py-1.5 text-xs font-medium text-bone hover:bg-elevate disabled:opacity-50"
                      >
                        {downloading === r.report_id ? (
                          <CircleNotch size={13} className="animate-spin" />
                        ) : (
                          <DownloadSimple size={13} />
                        )}
                        다운로드
                      </button>
                    ) : (
                      <span className="text-xs text-slatey">파일 없음</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
