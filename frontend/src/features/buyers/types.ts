// INC-8a 매수자(투자·금융사) 마스터 — backend /buyers 계약 (tb_buyer)
// buyer_type은 공통 코드 마스터(tb_code, category=SALE_BUYER_TYPE)로 관리 → 문자열.

export interface Buyer {
  project_count?: number // 참여 사업 수(거래계약 보유 distinct 사업)
  buyer_id: string
  name: string
  buyer_type?: string | null // SALE_BUYER_TYPE: 증권사/투자사/금융사/기타
  biz_reg_no?: string | null
  contact_name?: string | null
  contact_phone?: string | null
  contact_email?: string | null
  memo?: string | null
  created_at?: string | null
  updated_at?: string | null
}

/** 매수자 등록/수정 payload (schemas.BuyerIn / BuyerUpdate) */
export interface BuyerPayload {
  name: string
  buyer_type?: string | null
  biz_reg_no?: string | null
  contact_name?: string | null
  contact_phone?: string | null
  contact_email?: string | null
  memo?: string | null
}
