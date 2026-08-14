// P4 정산 관리 API 훅 — backend routers/settlements.py 계약 준수.
// 조회는 get_current_user(내부, OBSERVER 403), 확정·상태전이는 settlement.change(MANAGER↑),
// 청구취소(BILLED→CONFIRMED)는 ADMIN 전용(백엔드가 별도 게이트).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import type {
  PipelineFilters,
  PipelineResponse,
  SettlementConfirmRequest,
  SettlementFilters,
  SettlementListResponse,
  SettlementOut,
  SettlementSnapshotListResponse,
  SettlementStatusUpdate,
} from './types'

/** 정산 헤더 목록(확정 이후만) — 필터 client_id·project_id·status */
export function useSettlements(filters: SettlementFilters) {
  return useQuery({
    queryKey: ['settlements', filters],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (filters.client_id) params.client_id = filters.client_id
      if (filters.project_id) params.project_id = filters.project_id
      if (filters.status) params.status = filters.status
      const { data } = await api.get<SettlementListResponse>('/settlements', { params })
      return data
    },
    placeholderData: (prev) => prev, // 필터 전환 시 이전 결과 유지(깜빡임 방지)
  })
}

/** 정산 회차 스냅샷(append-only 감사) — seq 오름차순. 행 펼침 시에만 조회 */
export function useSettlementSnapshots(settlementId: string | null | undefined) {
  return useQuery({
    queryKey: ['settlements', 'snapshots', settlementId],
    queryFn: async () => {
      const { data } = await api.get<SettlementSnapshotListResponse>(
        `/settlements/${settlementId}/snapshots`,
      )
      return data
    },
    enabled: !!settlementId,
  })
}

/** 정산 확정(freeze) — 예정→CONFIRMED. settlement.change(MANAGER↑). 201 */
export function useConfirmSettlement() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: SettlementConfirmRequest) => {
      const { data } = await api.post<SettlementOut>('/settlements/confirm', payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settlements'] })
    },
  })
}

/** 정산 상태전이 — CONFIRMED→BILLED→COMPLETED, 청구취소 BILLED→CONFIRMED(ADMIN). settlement.change */
export function useUpdateSettlementStatus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ settlement_id, target_status, reason }: SettlementStatusUpdate) => {
      const { data } = await api.put<SettlementOut>(`/settlements/${settlement_id}/status`, {
        target_status,
        reason: reason?.trim() || undefined,
      })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settlements'] })
    },
  })
}

/** 파이프라인 현황(내부 전용) — (운수사×사업) 5단계 진행 파생. 필터 client_id·project_id·status */
export function usePipeline(filters: PipelineFilters) {
  return useQuery({
    queryKey: ['settlements', 'pipeline', filters],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (filters.client_id) params.client_id = filters.client_id
      if (filters.project_id) params.project_id = filters.project_id
      if (filters.settlement_status) params.settlement_status = filters.settlement_status
      const { data } = await api.get<PipelineResponse>('/settlements/pipeline', { params })
      return data
    },
    placeholderData: (prev) => prev,
  })
}
