// AV-3 전기버스 자산 — 자산관리 크로스-프로젝트 차량 목록 계약 (backend GET /asset-vehicles)

/** 차량 1행 — 소속 사업 회계값(project_revenue/cost)은 차량 안분이 아니라 사업 원문(D1-A) */
export interface AssetVehicleRow {
  vehicle_id: string
  project_id: string
  project_name: string | null
  vehicle_no: string | null
  region: string | null
  client_id: string | null
  client_name: string | null
  registered_at: string | null
  expire_at: string | null
  approved_at: string | null
  total_reduction: number | null
  remaining_age: number | null
  effective_reduction: number | null
  expected_payout: number | null
  project_status: string | null
  approval_status: string | null
  // 연차별 감축량(AV-4 상세 펼침에서 재사용)
  reduction_y1: number | null
  reduction_y2: number | null
  reduction_y3: number | null
  reduction_y4: number | null
  reduction_y5: number | null
  reduction_y6: number | null
  reduction_y7: number | null
  reduction_y8: number | null
  reduction_y9: number | null
  reduction_y10: number | null
  // 소속 사업 회계값(사업 그레인 — 헤더 "(사업)" 표기)
  project_revenue: number | null
  project_cost: number | null
}

/** 상단 KPI — 재무 3종(revenue/cost/profit)은 필터 걸린 distinct 사업 전체 기준(D2, 차량 KPI와 그레인 다름) */
export interface AssetVehicleKpi {
  vehicle_count: number | null
  total_reduction: number | null
  effective_reduction_sum: number | null
  expected_payout_sum: number | null
  revenue: number | null
  cost: number | null
  profit: number | null
}

export interface AssetVehicleListResponse {
  items: AssetVehicleRow[]
  total: number
  kpi: AssetVehicleKpi
}

export interface AssetVehicleFilters {
  project_id?: string
  region?: string
  /** '__none__' = 운수사 미지정 */
  client_id?: string
  approval_status?: string
  buyer_id?: string
  /** YYYY-MM-DD */
  registered_from?: string
  registered_to?: string
  /** YYYY-MM-DD — 차령만료 임박(이 날짜 이전 만료) */
  expire_before?: string
  search?: string
  page: number
  page_size: number
}
