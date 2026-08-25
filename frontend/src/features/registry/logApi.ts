// 차량 월별 운행·충전 로그 API — backend/routers/vehicle_logs.py (D6, P1·P2)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'

export interface ConsolidateRow {
  vehicle_no: string
  operator_name?: string | null
  has_run: boolean
  has_charge: boolean
  months: Record<string, { operating_days: number | null; distance_km: number | null; charge_kwh: number | null }>
}
export interface ConsolidateResp {
  months: string[]
  vehicles: ConsolidateRow[]
  vehicle_count: number
  missing_run: number
  missing_charge: number
}
export interface AggregateItem {
  vehicle_no: string
  status: string
  reason?: string | null
  project_distance?: number | null
  project_kwh?: number | null
  months_used?: number | null
}
export interface AggregateResp {
  vehicle_count: number
  aggregated: number
  insufficient: number
  updated: number
  created: number
  items: AggregateItem[]
}

export function useConsolidate(params: { program_only?: boolean; region?: string }) {
  return useQuery({
    queryKey: ['vehicle-logs-consolidate', params],
    queryFn: async () =>
      (await api.get<ConsolidateResp>('/vehicle-logs/consolidate', { params })).data,
  })
}

export function useImportVehicleLogs() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData(); fd.append('file', file)
      const { data } = await api.post('/vehicle-logs/import', fd)
      return data as { created: number; updated: number; client_matched: number; vehicles: number; months: number; total: number }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vehicle-logs-consolidate'] }),
  })
}

export interface RawImportResult {
  files: number
  parsed_files: number
  skipped_files: string[]
  created: number
  updated: number
  client_matched: number
  vehicles: number
  months: number
  total: number
}
export function useImportRawLogs() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (files: FileList) => {
      const fd = new FormData()
      Array.from(files).forEach((f) => fd.append('files', f))
      const { data } = await api.post('/vehicle-logs/import-raw', fd)
      return data as RawImportResult
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['vehicle-logs-consolidate'] }),
  })
}

export function useAggregateLogs() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (commit: boolean) => {
      const { data } = await api.post('/vehicle-logs/aggregate', null, { params: { commit_project: commit } })
      return data as AggregateResp
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vehicle-logs-consolidate'] })
      qc.invalidateQueries({ queryKey: ['reduction-run'] })
    },
  })
}
