// 차량 통합 상세(dossier, 개편 P5) — GET /vehicles/{vehicle_no}/dossier
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api/client'

export interface VehicleDossier {
  vehicle_no: string
  found: boolean
  owned: Array<{
    vehicle_id: string; client_id: string | null; operator_name: string | null
    region: string | null; chassis_no: string | null; model_name: string | null
    model_year: number | null; vehicle_class: string | null; fuel: string | null
    seating_capacity: number | null; status: string | null
  }>
  participations: Array<{
    project_id: string | null; project_name: string | null; project_status: string | null
    introduction_type: string | null; total_reduction: number | null
    effective_reduction: number | null; expected_payout: number | null
    private_invest_ratio: number | null
  }>
  registry: Array<{ role: string | null; vin: string | null; introduction_type: string | null; region: string | null }>
  calc_input: {
    introduction_type: string | null; vin_status: string | null; fuel: string | null
    baseline_distance: number | null; baseline_fuel: number | null
    project_distance: number | null; project_kwh: number | null
    ev_reg_year: number | null; private_ratio: number | null
  } | null
  stages: Record<string, { total_reduction: number | null; adjusted_total: number | null; project_distance: number | null; project_kwh: number | null }>
  log_summary: {
    month_from: string | null; month_to: string | null; month_count: number
    sources: string[]; total_distance: number; total_charge: number; has_charge: boolean
  } | null
  finance: {
    vehicle_value: number | null; self_payment: number | null; private_ratio: number | null
    public_ratio: number | null; ev_subsidy: number | null
  } | null
}

export function useVehicleDossier(vehicleNo: string | undefined) {
  return useQuery({
    queryKey: ['vehicle-dossier', vehicleNo],
    queryFn: async () =>
      (await api.get<VehicleDossier>(`/vehicles/${encodeURIComponent(vehicleNo!)}/dossier`)).data,
    enabled: !!vehicleNo,
  })
}
