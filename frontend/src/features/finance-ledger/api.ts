// FL-3 재무 원장 API 훅 — backend GET /finance-ledger 계약 준수
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import type { FinanceLedgerFilters, FinanceLedgerListResponse } from './types'

export function useFinanceLedger(filters: FinanceLedgerFilters) {
  return useQuery({
    queryKey: ['finance-ledger', filters],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page: filters.page,
        page_size: filters.page_size,
      }
      if (filters.approval_status) params.approval_status = filters.approval_status
      if (filters.client_id) params.client_id = filters.client_id
      if (filters.buyer_id) params.buyer_id = filters.buyer_id
      if (filters.is_hold) params.is_hold = filters.is_hold
      if (filters.invoice_from) params.invoice_from = filters.invoice_from
      if (filters.invoice_to) params.invoice_to = filters.invoice_to
      if (filters.search) params.search = filters.search
      const { data } = await api.get<FinanceLedgerListResponse>('/finance-ledger', { params })
      return data
    },
    placeholderData: (prev) => prev, // 페이지·필터 전환 시 이전 결과 유지(깜빡임 방지)
  })
}
