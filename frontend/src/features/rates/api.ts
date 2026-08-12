// 매출단가 시세(effective-dated) API 훅 — backend/routers/market_rates.py 실계약 기준
// GET  /market-rates          → MarketRateOut[] (effective_date desc, created_at desc)
// GET  /market-rates/current  → {effective_date, unit_price} | null (유효일자 ≤ 오늘 최신)
// POST /market-rates {effective_date, unit_price, note?} → MarketRateOut (같은 일자 append 허용)
// 매출단가는 내부 재무정보 — 조회도 내부 인증만(외부역할 자동 403), 등록은 master.write.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'

export interface MarketRate {
  rate_id: string
  effective_date: string
  unit_price: number
  note?: string | null
  created_by?: string | null
  created_at?: string | null
}

export interface CurrentRate {
  effective_date: string
  unit_price: number
}

export interface MarketRatePayload {
  effective_date: string
  unit_price: number
  note?: string | null
}

export function useMarketRates(enabled = true) {
  return useQuery({
    queryKey: ['market-rates'],
    queryFn: async () => {
      const { data } = await api.get<MarketRate[]>('/market-rates')
      return data
    },
    enabled,
  })
}

export function useCurrentRate(enabled = true) {
  return useQuery({
    queryKey: ['market-rates', 'current'],
    queryFn: async () => {
      const { data } = await api.get<CurrentRate | null>('/market-rates/current')
      return data
    },
    enabled,
  })
}

export function useCreateMarketRate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: MarketRatePayload) => {
      const { data } = await api.post<MarketRate>('/market-rates', payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['market-rates'] })
      // 시세 변경은 프로젝트 상세의 재고평가(비영속 파생)에 영향 — 관련 캐시 무효화
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}
