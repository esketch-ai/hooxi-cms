// 방법론 상수 마스터 API — backend/routers/methodology.py
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'

export interface MethodologyConstant {
  const_id: string
  key: string
  value: number
  unit?: string | null
  label?: string | null
  effective_date: string
  note?: string | null
}
export interface MethodologyConstantPayload {
  key: string
  value: number
  unit?: string | null
  label?: string | null
  effective_date: string
  note?: string | null
}

export function useMethodologyConstants(enabled = true) {
  return useQuery({
    queryKey: ['methodology-constants'],
    enabled,
    queryFn: async () => (await api.get<MethodologyConstant[]>('/methodology-constants')).data,
  })
}
export function useCreateMethodologyConstant() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (p: MethodologyConstantPayload) =>
      (await api.post<MethodologyConstant>('/methodology-constants', p)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['methodology-constants'] }),
  })
}
