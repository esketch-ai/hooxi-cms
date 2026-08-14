// P4 정산 관리(SCR-07) — 정산 헤더 상태전이·스냅샷 이력·파이프라인 현황 계약.
// backend routers/settlements.py 계약 준수. 그레인=(고객사×사업[×기간]).
// 예정은 lazy(header 없음), 최초 확정 시 tb_settlement 1건 생성. 상태머신:
// (예정) → 확정 CONFIRMED → 청구 BILLED → 입금완료 COMPLETED. 청구취소 BILLED→CONFIRMED(ADMIN).

/** 정산 상태 코드값(SETTLEMENT_STATUS) — 헤더 존재 시 CONFIRMED 이상 */
export type SettlementStatus = 'STANDBY' | 'CONFIRMED' | 'BILLED' | 'COMPLETED'

/** 정산 헤더 1건 — 확정 시 동결된 지표·상태·감사 시각 포함(SettlementOut) */
export interface SettlementOut {
  settlement_id: string
  client_id: string
  project_id: string
  period: string | null // 'YYYY-MM' — 단일 정산이면 null
  status: string // CONFIRMED/BILLED/COMPLETED (SETTLEMENT_STATUS)
  confirmed_amount: number | null
  vehicle_count: number | null // 확정 시점 동결
  effective_reduction: number | null // 확정 시점 동결
  confirmed_at: string | null
  confirmed_by: string | null
  billed_at: string | null
  billed_by: string | null
  completed_at: string | null
  completed_by: string | null
  paid_amount: number | null // 완료 시 실입금액
  payment_type: string | null // 지급 구분 코드값
  created_at: string | null
  updated_at: string | null
}

export interface SettlementListResponse {
  items: SettlementOut[]
  total: number
}

export interface SettlementFilters {
  client_id?: string
  project_id?: string
  status?: string
}

/** 정산 스냅샷 1회차(append-only 감사) — 확정/청구/입금/취소 시점 동결 금액의 정본 */
export interface SettlementSnapshotOut {
  snapshot_id: string
  map_id: string // settlement_id(재활용 감사키)
  seq: number
  issued_credits: number | null
  amount: number | null
  unit_price: number | null
  allocation_ratio: number | null
  success_fee_rate: number | null
  paid_amount: number | null
  vehicle_count: number | null
  effective_reduction: number | null
  action: string // CONFIRMED/BILLED/REBILLED/REVERTED/COMPLETED
  reason: string | null
  created_by: string | null
  created_at: string | null
}

export interface SettlementSnapshotListResponse {
  items: SettlementSnapshotOut[]
  total: number
}

/** 확정(freeze) 요청 — (고객사×사업[×기간]) 예정 정산을 CONFIRMED로 동결 */
export interface SettlementConfirmRequest {
  client_id: string
  project_id: string
  period?: string // 'YYYY-MM' — 단일 정산이면 미지정
}

/** 상태전이 요청 — target_status는 SETTLEMENT_STATUS 코드값. 청구취소는 reason 필수(ADMIN) */
export interface SettlementStatusUpdate {
  settlement_id: string
  target_status: SettlementStatus
  reason?: string
}

// ── 파이프라인 현황판(증분4 backend) — (운수사×사업) 5단계 진행 파생(조회 전용) ──

/** 파이프라인 단계 코드 — 현재 최고 도달 단계 */
export type PipelineStage =
  | 'none'
  | 'collect'
  | 'accounting'
  | 'settlement'
  | 'report'
  | 'notice'

/** (운수사×사업) 파이프라인 1행 — 수집→결산→정산→보고→통지 5단계 파생 현황 */
export interface PipelineRow {
  client_id: string | null // null=(미지정) 셀(통지 불가)
  company_name: string
  project_id: string
  project_name: string
  vehicle_count: number
  has_accounting: boolean // 결산 완료 신호(expected_payout non-null 차량 존재)
  settlement_status: string | null // null=예정 / CONFIRMED·BILLED·COMPLETED
  reported: boolean // 보고 감사 존재(전역 약한 신호)
  notified: boolean // 통지 이력/감사 존재
  stage: PipelineStage // 현재 최고 도달 단계 코드
  next_action: string // 다음 할일 안내
}

export interface PipelineResponse {
  items: PipelineRow[]
  total: number
  stage_counts?: Record<string, number> | null // 단계 코드별 행 수(요약)
}

export interface PipelineFilters {
  client_id?: string
  project_id?: string
  settlement_status?: string
}
