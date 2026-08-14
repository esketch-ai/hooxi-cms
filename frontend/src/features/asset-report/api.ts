// P2 자산관리 보고 API 훅 — backend GET /asset-report/settlement-summary 계약 준수
// export(xlsx)는 downloadExport를 화면에서 직접 호출한다(팀장↑ 게이트와 정합).
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import type {
  SettlementNoticePreview,
  SettlementNoticePreviewPayload,
  SettlementNoticeSendPayload,
  SettlementNoticeSendResult,
  SettlementSummaryFilters,
  SettlementSummaryResponse,
} from './types'

export function useSettlementSummary(filters: SettlementSummaryFilters) {
  return useQuery({
    queryKey: ['asset-report/settlement-summary', filters],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (filters.client_id) params.client_id = filters.client_id
      if (filters.client_type) params.client_type = filters.client_type
      if (filters.region) params.region = filters.region
      const { data } = await api.get<SettlementSummaryResponse>(
        '/asset-report/settlement-summary',
        { params },
      )
      return data
    },
    placeholderData: (prev) => prev, // 필터 전환 시 이전 결과 유지(깜빡임 방지)
  })
}

// ── P3 정산 통지 — master.write 전용. 성공/실패 토스트는 화면에서 처리 ──

/** 통지 대상 미리보기 — POST(조회 성격). 대상·수신가능·발송가능 수 반환.
 *  notice_type(예정/확정)에 따라 대상·금액 원천이 달라진다(백엔드 분기). */
export function useSettlementNoticePreview() {
  return useMutation({
    mutationFn: async (payload: SettlementNoticePreviewPayload) => {
      const body: Record<string, string> = {}
      if (payload.client_id) body.client_id = payload.client_id
      if (payload.client_type) body.client_type = payload.client_type
      if (payload.region) body.region = payload.region
      if (payload.notice_type) body.notice_type = payload.notice_type
      const { data } = await api.post<SettlementNoticePreview>(
        '/asset-report/settlement-notice/preview',
        body,
      )
      return data
    },
  })
}

/** 통지 발송 — 건별 메일 발송으로 오래 걸릴 수 있어 timeout 상향(배치 관용구).
 *  Gmail 미설정 시 503 — 호출부에서 서버 detail 토스트 안내 */
export function useSettlementNoticeSend() {
  return useMutation({
    mutationFn: async (payload: SettlementNoticeSendPayload) => {
      const { data } = await api.post<SettlementNoticeSendResult>(
        '/asset-report/settlement-notice/send',
        payload,
        { timeout: 120_000 },
      )
      return data
    },
  })
}
