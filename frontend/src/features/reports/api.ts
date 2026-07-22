// SCR-12 월간 보고서 발송 관리 API 훅 — 플랜 §5 SCR-12 엔드포인트
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import type { ReportDelivery, ReportListResponse, ReportStatus } from '../../types'

export function useReports(period: string) {
  return useQuery({
    queryKey: ['reports', period],
    queryFn: async () => {
      const { data } = await api.get<ReportListResponse>('/reports', {
        params: { period },
      })
      return data
    },
  })
}

/** 행 Drawer 상세 — 버전 히스토리·발송 기록 포함 */
export function useReportDetail(reportId: string | undefined) {
  return useQuery({
    queryKey: ['reports', 'detail', reportId],
    queryFn: async () => {
      const { data } = await api.get<ReportDelivery>(`/reports/${reportId}`)
      return data
    },
    enabled: !!reportId,
  })
}

function useInvalidateReports() {
  const queryClient = useQueryClient()
  return (reportId?: string) => {
    queryClient.invalidateQueries({ queryKey: ['reports'] })
    // 대시보드 '오늘의 액션'의 보고서 소스(['dashboard','reports',…])도 함께 갱신
    queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    if (reportId) {
      queryClient.invalidateQueries({ queryKey: ['reports', 'detail', reportId] })
    }
  }
}

/** 파일 업로드 — POST /reports/{id}/file (tb_document 버전 적재) */
export function useUploadReportFile() {
  const invalidate = useInvalidateReports()
  return useMutation({
    mutationFn: async ({ reportId, file }: { reportId: string; file: File }) => {
      const form = new FormData()
      form.append('file', file)
      const { data } = await api.post(`/reports/${reportId}/file`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60_000,
      })
      return data
    },
    onSuccess: (_data, v) => invalidate(v.reportId),
  })
}

/** 발송 — POST /reports/{id}/send (Gmail + 카카오 연동 시 알림톡 병행).
 *  dropboxPaths: 발송 시 추가 첨부할 고객사 Dropbox 파일 경로(라이브 브라우즈 선택). */
export function useSendReport() {
  const invalidate = useInvalidateReports()
  return useMutation({
    mutationFn: async ({
      reportId,
      dropboxPaths,
    }: {
      reportId: string
      dropboxPaths?: string[]
    }) => {
      const { data } = await api.post(
        `/reports/${reportId}/send`,
        { dropbox_attachment_paths: dropboxPaths?.length ? dropboxPaths : null },
        { timeout: 60_000 },
      )
      return data
    },
    onSuccess: (_data, vars) => invalidate(vars.reportId),
  })
}

/** 발송 고정본 지정/해제 — PUT /reports/{id}/pin (R2-B4, doc_id=null이면 해제) */
export function usePinReportDocument() {
  const invalidate = useInvalidateReports()
  return useMutation({
    mutationFn: async ({ reportId, docId }: { reportId: string; docId: string | null }) => {
      const { data } = await api.put(`/reports/${reportId}/pin`, { doc_id: docId })
      return data
    },
    onSuccess: (_data, v) => invalidate(v.reportId),
  })
}

/** 상태 변경 — PUT /reports/{id}/status */
export function useChangeReportStatus() {
  const invalidate = useInvalidateReports()
  return useMutation({
    mutationFn: async ({
      reportId,
      status,
      confirm_basis,
    }: {
      reportId: string
      status: ReportStatus
      confirm_basis?: string
    }) => {
      const { data } = await api.put(`/reports/${reportId}/status`, {
        status,
        ...(confirm_basis ? { confirm_basis } : {}),
      })
      return data
    },
    onSuccess: (_data, v) => invalidate(v.reportId),
  })
}

/** 월초 배치 수동 실행 응답 (schemas.ReportSendBatchResponse) */
export interface ReportSendBatchResult {
  period: string
  generated_created: number
  generated_skipped: number
  targets: number
  sent: number
  failed: number
}

/** 월초 배치 수동 실행 — POST /batch/report-send (ADMIN 토큰, 전월 APPROVED 일괄 발송) */
export function useRunReportSendBatch() {
  const invalidate = useInvalidateReports()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<ReportSendBatchResult>('/batch/report-send', null, {
        timeout: 120_000,
      })
      return data
    },
    onSuccess: () => invalidate(),
  })
}

/** 당월 발송 대상 생성 — POST /reports/generate?period= (구독 활성 + report_yn=Y 기반, 멱등) */
export function useGenerateReports() {
  const invalidate = useInvalidateReports()
  return useMutation({
    mutationFn: async (period: string) => {
      // period는 쿼리 파라미터 (routers/reports.py generate_reports)
      const { data } = await api.post('/reports/generate', null, { params: { period } })
      return data
    },
    onSuccess: () => invalidate(),
  })
}
