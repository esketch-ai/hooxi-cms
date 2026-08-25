// 전기버스 도입 재무(민간투자비율 근거) API — backend/routers/ev_finance.py
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'

export interface EvFinanceItem {
  ev_finance_id: string
  vehicle_no?: string | null
  operator_name?: string | null
  client_name?: string | null
  region?: string | null
  release_price?: number | null
  vehicle_value?: number | null
  low_floor_subsidy?: number | null
  ev_subsidy?: number | null
  self_payment?: number | null
  private_ratio?: number | null
  public_ratio?: number | null
  subsidy_check?: number | null
  note?: string | null
}

export interface EvFinanceSummary {
  count: number
  vehicle_value_total: number
  subsidy_total: number
  self_payment_total: number
  avg_private_ratio: number
}

export function useEvFinance(params: { region?: string; search?: string; page: number; page_size: number }) {
  return useQuery({
    queryKey: ['ev-finance', params],
    queryFn: async () => {
      const q: Record<string, string | number> = { page: params.page, page_size: params.page_size }
      if (params.region) q.region = params.region
      if (params.search) q.search = params.search
      const { data } = await api.get<{ items: EvFinanceItem[]; total: number }>('/ev-finance', { params: q })
      return data
    },
    placeholderData: (p) => p,
  })
}

export function useEvFinanceSummary() {
  return useQuery({
    queryKey: ['ev-finance', 'summary'],
    queryFn: async () => (await api.get<EvFinanceSummary>('/ev-finance/summary')).data,
  })
}

export function useImportEvFinance() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      const { data } = await api.post('/ev-finance/import', fd)
      return data as { created: number; client_matched: number }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ev-finance'] }),
  })
}
