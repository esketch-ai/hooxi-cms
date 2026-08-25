// 감축 참여 레지스트리(KISA 500대) API — backend/routers/reduction_registry.py
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'

export interface RegistryItem {
  registry_id: string
  role: string // BASELINE | PROJECT | CANDIDATE
  vehicle_no?: string | null
  operator_name?: string | null
  client_id?: string | null
  client_name?: string | null
  introduction_type?: string | null
  model_name?: string | null
  vin?: string | null
  model_year?: number | null
  vehicle_class?: string | null
  purpose?: string | null
  seating_capacity?: number | null
  fuel?: string | null
  registered_at?: string | null
  battery_type?: string | null
  program_name?: string | null
  region?: string | null
}

export interface RegistrySummary {
  total: number
  baseline: number
  project: number
  candidate: number
  client_matched: number
  by_region: { region: string; count: number }[]
}

export interface RegistryFilters {
  role?: string
  region?: string
  introduction_type?: string
  search?: string
  page: number
  page_size: number
}

export function useRegistry(filters: RegistryFilters) {
  return useQuery({
    queryKey: ['registry', filters],
    queryFn: async () => {
      const params: Record<string, string | number> = { page: filters.page, page_size: filters.page_size }
      if (filters.role) params.role = filters.role
      if (filters.region) params.region = filters.region
      if (filters.introduction_type) params.introduction_type = filters.introduction_type
      if (filters.search) params.search = filters.search
      const { data } = await api.get<{ items: RegistryItem[]; total: number }>('/reduction-registry', { params })
      return data
    },
    placeholderData: (p) => p,
  })
}

export function useRegistrySummary() {
  return useQuery({
    queryKey: ['registry', 'summary'],
    queryFn: async () => (await api.get<RegistrySummary>('/reduction-registry/summary')).data,
  })
}

export function useImportRegistry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      const { data } = await api.post('/reduction-registry/import', fd)
      return data as { created: number; client_matched: number; baseline: number; project: number; candidate: number }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['registry'] }),
  })
}
