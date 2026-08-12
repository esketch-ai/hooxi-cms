// FL-3 재무 원장 — 전 감축사업을 '사업 grain'으로 집계한 재무 원장 계약 (backend GET /finance-ledger)
// cf. AV-3 전기버스 자산은 '차량 grain' — grain이 다르므로 화면 subtitle로 구분 명시.

/** 재무 원장 1행 — 사업 단위. 회계 12값 + 후시/계약 분할값(펼침 상세). 금액 nullable */
export interface FinanceLedgerRow {
  project_id: string
  project_name: string | null
  /** 사업번호 */
  reg_code: string | null
  approval_status: string | null
  approved_at: string | null
  // ── 회계 체인 12값 ──────────────────────────────────────────────
  /** 제품(총매입) */
  product: number | null
  /** 예상지급액 */
  expected_payment: number | null
  /** 미착품1 */
  wip1: number | null
  /** 미착품2 */
  wip2: number | null
  /** 부채 */
  liability: number | null
  /** 재고자산 */
  inventory: number | null
  /** 지급률 0~1 */
  payout_rate: number | null
  /** 매출인식 */
  sale_recognized: number | null
  /** 매출이익 */
  gross_profit: number | null
  /** 이익률 0~1 */
  profit_rate: number | null
  /** 소유권비율합 */
  ownership_total: number | null
  // ── 후시/계약 분할(펼침 상세, D2) ───────────────────────────────
  held_qty: number | null
  sold_qty: number | null
  held_ownership: number | null
  sold_ownership: number | null
  /** 재고평가(현재시세 기준) */
  inventory_valuation: number | null
}

/** 총계 — 필터 기준 전 사업 합 */
export interface FinanceLedgerTotals {
  product: number | null
  expected_payment: number | null
  wip1: number | null
  wip2: number | null
  liability: number | null
  inventory: number | null
  sale_recognized: number | null
  gross_profit: number | null
  profit_rate: number | null
  held_qty: number | null
  inventory_valuation: number | null
}

export interface FinanceLedgerListResponse {
  items: FinanceLedgerRow[]
  total: number
  totals: FinanceLedgerTotals
  /** 현재 매출단가 시세(원/tCO2) — 재고평가 기준. 미등록 시 null */
  current_market_rate: number | null
}

export interface FinanceLedgerFilters {
  approval_status?: string
  client_id?: string
  buyer_id?: string
  /** 후시보유 필터 — 'Y'만 사용 */
  is_hold?: string
  /** 매출세금계산서 발행일 from (YYYY-MM-DD) */
  invoice_from?: string
  invoice_to?: string
  /** 사업명·사업번호 검색 */
  search?: string
  page: number
  page_size: number
}
