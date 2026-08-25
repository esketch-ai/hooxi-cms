// 세금계산서 원장(홈택스 HTML 자동반영) — 타입

export interface TaxInvoicePreviewItem {
  filename?: string | null
  ok: boolean
  reason?: string | null // password_unresolved / header_missing / decrypt_or_parse_error
  approval_no?: string | null
  direction?: string | null // 매입/매출/미상
  issue_date?: string | null // YYYY-MM-DD
  invoicer_reg_no?: string | null
  invoicee_reg_no?: string | null
  invoicer_name?: string | null
  invoicee_name?: string | null
  counterpart_reg_no?: string | null
  counterpart_name?: string | null
  supply_amount?: number | null
  tax_amount?: number | null
  total_amount?: number | null
  type_code?: string | null
  purpose_code?: string | null
  matched_client_id?: string | null
  matched_client_name?: string | null
  matched_buyer_id?: string | null
  matched_buyer_name?: string | null
  is_duplicate?: boolean | null
}

export interface TaxInvoicePreviewResponse {
  items: TaxInvoicePreviewItem[]
}

export interface TaxInvoiceCommitDetail {
  filename?: string | null
  result: string // created / duplicate / held
  reason?: string | null
  approval_no?: string | null
  tax_invoice_id?: string | null
}

export interface TaxInvoiceCommitResponse {
  total: number
  created: number
  duplicate: number
  held: number
  details: TaxInvoiceCommitDetail[]
}

export interface TaxInvoice {
  tax_invoice_id: string
  approval_no?: string | null
  direction?: string | null
  invoicer_reg_no?: string | null
  invoicee_reg_no?: string | null
  invoicer_name?: string | null
  invoicee_name?: string | null
  counterpart_reg_no?: string | null
  counterpart_name?: string | null
  issue_date?: string | null
  supply_amount?: number | null
  tax_amount?: number | null
  total_amount?: number | null
  type_code?: string | null
  purpose_code?: string | null
  matched_client_id?: string | null
  matched_buyer_id?: string | null
  project_id?: string | null
  source?: string | null
  created_at?: string | null
}

export interface TaxInvoiceListResponse {
  items: TaxInvoice[]
  total: number
}

export interface TaxInvoiceFilters {
  direction?: string
  search?: string
  issue?: string // unlinked | unmatched | negative
  page: number
  page_size: number
}

export interface TaxInvoiceIssueCounts {
  unlinked: number
  unmatched: number
  negative: number
}

export interface TaxInvoiceMonthPoint {
  month: string
  purchase: number
  sales: number
  net: number
}

export interface TaxInvoiceSummary {
  purchase_supply: number
  sales_supply: number
  net_supply: number
  purchase_tax: number
  sales_tax: number
  purchase_count: number
  sales_count: number
  months: TaxInvoiceMonthPoint[]
}

export interface TaxInvoiceBreakdownRow {
  key: string
  label: string
  purchase: number
  sales: number
  net: number
  count: number
}

export interface TaxInvoiceBreakdown {
  axis: string
  rows: TaxInvoiceBreakdownRow[]
}
