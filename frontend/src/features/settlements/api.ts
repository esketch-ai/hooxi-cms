// SCR-07 고객사별 정산 현황 API 훅 — backend/routers/settlements.py 계약 준수
// (쿼리 파라미터: settlement_status / project_id / period, 본문: settlement_status)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import type { ProjectClientMap, SettlementStatus } from '../../types'

export interface SettlementFilters {
  settlement_status?: string
  project_id?: string
  /** 정산 기준월 'YYYY-MM' — 청구월(billed_at) 우선, STANDBY는 예상 발급월 */
  period?: string
  page: number
  page_size: number
}

interface SettlementListResponse {
  items?: ProjectClientMap[]
  total?: number
}

export function useSettlements(filters: SettlementFilters) {
  return useQuery({
    queryKey: ['settlements', filters],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page: filters.page,
        page_size: filters.page_size,
      }
      if (filters.settlement_status) params.settlement_status = filters.settlement_status
      if (filters.project_id) params.project_id = filters.project_id
      if (filters.period) params.period = filters.period
      const { data } = await api.get<SettlementListResponse>('/settlements', { params })
      return {
        items: data.items ?? [],
        total: data.total ?? data.items?.length ?? 0,
      }
    },
  })
}

/** 정산 상태 전이 — STANDBY→BILLED→COMPLETED(역행 409). MANAGER 이상 (§10.1) */
export function useUpdateSettlementStatus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ mapId, status }: { mapId: string; status: SettlementStatus }) => {
      const { data } = await api.put<ProjectClientMap>(`/settlements/${mapId}/status`, {
        settlement_status: status,
      })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settlements'] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}
