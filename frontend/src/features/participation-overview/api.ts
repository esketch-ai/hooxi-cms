// 운수사별 감축 참여 크로스 집계(라이프사이클 보) — GET /clients/participation-overview
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api/client'

export interface OperatorRow {
  client_id: string
  operator_name: string | null
  region: string | null
  owned_count: number
  participating_count: number
  completed_count: number
  ongoing_count: number
  not_participated_count: number
  participation_rate: number | null
  expected_reduction: number
  monitoring_reduction: number
  final_reduction: number
  ach_monitoring: number | null
  ach_final: number | null
}
export interface ParticipationOverview {
  items: OperatorRow[]
  operator_count: number
  total_owned: number
  total_participating: number
  expected_total: number
  monitoring_total: number
  final_total: number
  participation_rate: number | null
}

export function useParticipationOverview(region?: string) {
  return useQuery({
    queryKey: ['participation-overview', region ?? ''],
    queryFn: async () =>
      (await api.get<ParticipationOverview>('/clients/participation-overview', {
        params: region ? { region } : {},
      })).data,
  })
}
