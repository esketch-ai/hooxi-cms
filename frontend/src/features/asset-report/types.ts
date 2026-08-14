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

// ── P3 정산 통지(메일) — 미리보기·발송 계약 (backend POST /asset-report/settlement-notice/*) ──
// master.write(STAFF/MANAGER/ADMIN) 전용. 미지정(미매칭) 운수사는 백엔드가 미리보기에서 제외한다.

/** 통지 유형(P4) — EXPECTED=live 예정액 고지 / CONFIRMED=확정 header(confirmed_amount) 고지.
 *  기본 EXPECTED(무회귀). CONFIRMED은 확정 header 있는 운수사만 백엔드가 대상으로 남긴다. */
export type SettlementNoticeType = 'EXPECTED' | 'CONFIRMED'

/** 통지 미리보기 1행 — 운수사 단위. can_receive=false면 수신자(공통/주담당 메일) 없음 */
export interface SettlementNoticePreviewItem {
  client_id: string
  company_name: string
  expected_payout?: number | null
  participating_vehicle_count: number
  participating_project_count: number
  can_receive: boolean
  to_count: number
}

export interface SettlementNoticePreview {
  items: SettlementNoticePreviewItem[]
  total: number
  /** 실제 발송 가능(수신자 보유) 운수사 수 */
  sendable_count: number
}

/** 통지 발송 결과 1건 — 운수사 단위 SENT/FAILED */
export interface SettlementNoticeSendDetail {
  client_id: string
  company_name: string
  result: 'SENT' | 'FAILED'
  reason?: string | null
}

export interface SettlementNoticeSendResult {
  target_count: number
  sent: number
  failed: number
  details: SettlementNoticeSendDetail[]
}

/** 발송 payload — client_ids 미지정 시 발송 가능 전체 대상, 제목/본문 미지정 시 기본 템플릿 */
export interface SettlementNoticeSendPayload {
  client_ids?: string[]
  subject?: string
  body?: string
  /** 통지 유형 — 미지정 시 백엔드 기본 EXPECTED */
  notice_type?: SettlementNoticeType
}

/** 미리보기 payload — 현재 필터 + 통지 유형(대상·금액 원천 분기) */
export interface SettlementNoticePreviewPayload extends SettlementSummaryFilters {
  notice_type?: SettlementNoticeType
}
