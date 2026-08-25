// 차량별 산정 입력 + 전차량 감축량 계산 API — backend/routers/reduction_calc_api.py
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'

export interface RunItem {
  vehicle_no: string
  operator_name?: string | null
  region?: string | null
  status: string
  reason?: string | null
  introduction_type?: string | null
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
export interface StageItem {
  vehicle_no: string
  operator_name?: string | null
  region?: string | null
  planned?: number | null
  monitoring?: number | null
  final?: number | null
  ach_monitoring?: number | null
  ach_final?: number | null
}
export interface StageCompareResp {
  items: StageItem[]
  vehicle_count: number
  total_planned: number
  total_monitoring: number
  total_final: number
}
export function useStageCompare() {
  return useQuery({
    queryKey: ['reduction-stage-compare'],
    queryFn: async () => (await api.get<StageCompareResp>('/reduction-stages/compare')).data,
  })
}
export function useSaveStage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (stage: 'PLANNED' | 'MONITORING' | 'FINAL') =>
      (await api.post(`/reduction-stages/${stage}`)).data as { stage: string; saved: number; skipped: number },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reduction-stage-compare'] }),
  })
}

// 차량 원장 링크 백필(정합 3) — 레지스트리·산정입력의 client_vehicle_id를 VIN 우선 매칭
export function useLinkBackfill() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      (await api.post('/vehicles/link-backfill')).data as {
        registry: Record<string, number>; calc_input: Record<string, number>
      },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reduction-run'] }),
  })
}

// 워크벤치 MONITORING 스냅샷 → 사업 정본(ProjectVehicle.monitoring_reduction) 단방향 커밋
export function useCommitMonitoring() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      (await api.post('/reduction-stages/commit-monitoring')).data as { committed: number; snapshots: number },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reduction-stage-compare'] })
      qc.invalidateQueries({ queryKey: ['clients'] }) // 운수사 감축 참여 탭 갱신
    },
  })
}

export function useImportCalcInputs() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData(); fd.append('file', file)
      const { data } = await api.post('/calc-inputs/import', fd)
      return data as { created: number; updated: number; client_matched: number; vin_ok: number; vin_warn: number; vin_new: number; total: number }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reduction-run'] }),
  })
}
