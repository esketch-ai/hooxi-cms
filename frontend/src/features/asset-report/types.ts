// P2 자산관리 보고 — 운수사(고객사)별 정산 예정 요약 계약 (backend GET /asset-report/settlement-summary)
// cf. FL-3 재무 원장은 '사업 grain', 여기는 '고객사 grain'으로 참여사업·차량·예상지급액을 집계.

/** 운수사 행 하위 드릴다운 — 참여 사업 1건 */
export interface SettlementProjectBreakdown {
  project_id: string
  project_name: string | null
  vehicle_count: number
  total_reduction: number | null
  effective_reduction: number | null
  expected_payout: number | null
}

/** 정산 요약 1행 — 고객사(운수사) 단위. 미매칭 고객은 client_id=null */
export interface SettlementSummaryRow {
  client_id: string | null
  company_name: string | null
  region: string | null
  client_type: string | null
  contract_status: string | null
  participating_project_count: number
  participating_vehicle_count: number
  total_reduction: number | null
  effective_reduction: number | null
  /** 예상지급액(정산예정) */
  expected_payout: number | null
  /** 행 펼침 드릴다운 — 이 운수사가 참여한 사업 목록 */
  projects: SettlementProjectBreakdown[]
}

/** 전사 총계 — 필터 기준 전 운수사 합 (사업수는 distinct) */
export interface SettlementSummaryTotals {
  distinct_project_count: number
  participating_vehicle_count: number
  total_reduction: number | null
  effective_reduction: number | null
  expected_payout: number | null
}

export interface SettlementSummaryResponse {
  items: SettlementSummaryRow[]
  total: number
  totals: SettlementSummaryTotals
}

export interface SettlementSummaryFilters {
  client_id?: string
  client_type?: string
  region?: string
}
