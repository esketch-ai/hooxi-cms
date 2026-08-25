// 충전 인프라(차고지·충전기·계) API — backend/routers/charging_infra.py
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'

export interface FacilityItem {
  facility_id: string
  operator_name?: string | null
  client_name?: string | null
  region?: string | null
  address?: string | null
  charger_count: number
  meter_count: number
}
export interface ChargingSummary {
  facilities: number
  chargers: number
  meters: number
  by_region: { region: string; count: number }[]
}

export function useFacilities(params: { region?: string; search?: string; page: number; page_size: number }) {
  return useQuery({
    queryKey: ['charging-infra', params],
    queryFn: async () => {
      const q: Record<string, string | number> = { page: params.page, page_size: params.page_size }
      if (params.region) q.region = params.region
      if (params.search) q.search = params.search
      const { data } = await api.get<{ items: FacilityItem[]; total: number }>('/charging-infra', { params: q })
      return data
    },
    placeholderData: (p) => p,
  })
}
export function useChargingSummary() {
  return useQuery({
    queryKey: ['charging-infra', 'summary'],
    queryFn: async () => (await api.get<ChargingSummary>('/charging-infra/summary')).data,
  })
}
export function useImportCharging() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData(); fd.append('file', file)
      const { data } = await api.post('/charging-infra/import', fd)
      return data as { facilities: number; chargers: number; meters: number; client_matched: number }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['charging-infra'] }),
  })
}
