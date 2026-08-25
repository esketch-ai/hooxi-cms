// 배출계수(EF) 마스터 API 훅 — backend/routers/emission_factors.py 실계약 기준
// GET /emission-factors          → EmissionFactor[] (연료·유효일자 최신순)
// GET /emission-factors/current  → EmissionFactor[] (연료별 현재값)
// POST /emission-factors {...}   → EmissionFactor (같은 연료·일자 append 허용)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'

export interface EmissionFactor {
  factor_id: string
  fuel_type: string
  ef_value: number
  unit?: string | null
  effective_date: string
  note?: string | null
  created_by?: string | null
  created_at?: string | null
}

export interface EmissionFactorPayload {
  fuel_type: string
  ef_value: number
  unit?: string | null
  effective_date: string
  note?: string | null
}

export function useEmissionFactors(enabled = true) {
  return useQuery({
    queryKey: ['emission-factors'],
    enabled,
    queryFn: async () => (await api.get<EmissionFactor[]>('/emission-factors')).data,
  })
}

export function useCurrentEmissionFactors(enabled = true) {
  return useQuery({
    queryKey: ['emission-factors', 'current'],
    enabled,
    queryFn: async () => (await api.get<EmissionFactor[]>('/emission-factors/current')).data,
  })
}

export function useCreateEmissionFactor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: EmissionFactorPayload) =>
      (await api.post<EmissionFactor>('/emission-factors', payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['emission-factors'] }),
  })
}
