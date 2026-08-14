// P2 자산관리 보고 API 훅 — backend GET /asset-report/settlement-summary 계약 준수
// export(xlsx)는 downloadExport를 화면에서 직접 호출한다(팀장↑ 게이트와 정합).
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import type { SettlementSummaryFilters, SettlementSummaryResponse } from './types'

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
