// Phase 4 외부 포털(PARTNER/INVESTOR) 전용 타입 — 백엔드 /portal/* 계약 shape 그대로 소비.
// 필드 가시성 규칙: PARTNER는 본인 데이터만, INVESTOR는 지급·원가·지급률 미포함(백엔드가 보장).

export type PortalRole = 'PARTNER' | 'INVESTOR'

export interface PortalMe {
  user_id: string
  name: string
  role: PortalRole
  org_name: string | null
}

export interface PortalProjectListItem {
  project_id: string
  project_name: string
  project_status: string
}

// 진행 단계 (내부 tb_project_stage와 동형)
export interface PortalStage {
  stage_code: string
  planned_date: string | null
  actual_date: string | null
  sort_order: number | null
  delayed: boolean
}

// PARTNER(운수사) 상세 — 본인 차량·감축·수혜금액만
export interface PartnerPortalView {
  project_id: string
  project_name: string
  project_status: string
  stages: PortalStage[]
  my_vehicle_count: number
  my_effective_reduction: number | null
  my_expected_payout: number | null
}

// INVESTOR(투자·금융사) 상세 — 운수사별 감축량(익명 라벨) + 자기 계약분. 지급·원가 없음.
export interface InvestorOperatorReduction {
  label: string
  vehicle_count: number
  effective_reduction: number | null
}

export interface InvestorContract {
  quantity: number | null
  gross_revenue: number | null
  sale_unit_price: number | null
  sale_invoice_amount: number | null
}

export interface InvestorPortalView {
  project_id: string
  project_name: string
  project_status: string
  stages: PortalStage[]
  operators_reduction: InvestorOperatorReduction[]
  total_effective_reduction: number | null
  total_contract_revenue: number | null
  my_contract: InvestorContract | null
}

// 역할별 상세 union
export type PortalProjectView = PartnerPortalView | InvestorPortalView

// 타임라인 — PARTNER는 expected_payout 포함, INVESTOR는 감축량만(옵셔널)
export interface PortalTimelinePoint {
  captured_at: string
  effective_reduction: number | null
  expected_payout?: number | null
}

// ── P1 운수사(PARTNER) 확장 ──
export interface PortalFleetItem {
  period: string
  license_count?: number | null
  total_count?: number | null
  diesel?: number | null
  cng?: number | null
  hybrid?: number | null
  electric?: number | null
  hydrogen?: number | null
  region?: string | null
  industry?: string | null
}

export interface PortalReportItem {
  report_id: string
  period: string
  report_type: string
  status: 'SENT' | 'CONFIRMED'
  sent_at?: string | null
  has_file: boolean
}

export interface PortalSettlementItem {
  settlement_id: string
  project_name?: string | null
  period?: string | null
  status: string
  confirmed_amount?: number | null
  vehicle_count?: number | null
  confirmed_at?: string | null
  completed_at?: string | null
  paid_amount?: number | null
}
