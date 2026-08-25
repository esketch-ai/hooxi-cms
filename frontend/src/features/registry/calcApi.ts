// 차량별 산정 입력 + 전차량 감축량 계산 API — backend/routers/reduction_calc_api.py
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'

export interface RunItem {
  vehicle_no: string
  operator_name?: string | null
  region?: string | null
  status: string
  reason?: string | null
  vin_status?: string | null
  fuel?: string | null
  usage_year?: number | null
  project_emission?: number | null
  total_reduction?: number | null
  private_ratio?: number | null
  adjusted_total?: number | null
  annual: number[]
}
export interface RunResp {
  computed: number
  skipped: number
  total: number
  total_reduction: number
  total_adjusted: number
  items: RunItem[]
}

export function useReductionRun(onlyOk: boolean) {
  return useQuery({
    queryKey: ['reduction-run', onlyOk],
    queryFn: async () =>
      (await api.get<RunResp>('/reduction-run', { params: { only_ok: onlyOk } })).data,
  })
}
export function useImportCalcInputs() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData(); fd.append('file', file)
      const { data } = await api.post('/calc-inputs/import', fd)
      return data as { created: number; updated: number; client_matched: number; vin_ok: number; vin_warn: number; total: number }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reduction-run'] }),
  })
}
