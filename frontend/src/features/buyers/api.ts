// INC-8a 매수자 마스터 API 훅 — 백엔드 /buyers 계약
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import { unwrapList } from '../../lib/api/queries'
import type { Paginated } from '../../types'
import type { Buyer, BuyerPayload } from './types'

export interface BuyerFilters {
  search?: string
  page: number
  page_size: number
}

export function useBuyers(filters: BuyerFilters) {
  return useQuery({
    queryKey: ['buyers', filters],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page: filters.page,
        page_size: filters.page_size,
      }
      if (filters.search) params.search = filters.search
      const { data } = await api.get<Buyer[] | Paginated<Buyer>>('/buyers', { params })
      return unwrapList(data)
    },
  })
}

/** 매수자 셀렉트 옵션용 전체 목록 (외부계정 발급·매출폼 재사용) */
export function useBuyerOptions() {
  return useQuery({
    queryKey: ['buyers', 'options'],
    queryFn: async () => {
      const { data } = await api.get<Buyer[] | Paginated<Buyer>>('/buyers', {
        params: { page_size: 200 },
      })
      return unwrapList(data).items
    },
    staleTime: 60_000,
  })
}

export function useSaveBuyer(buyerId?: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: BuyerPayload) => {
      const { data } = buyerId
        ? await api.put<Buyer>(`/buyers/${buyerId}`, payload)
        : await api.post<Buyer>('/buyers', payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['buyers'] })
    },
  })
}

export function useDeleteBuyer() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (buyerId: string) => {
      await api.delete(`/buyers/${buyerId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['buyers'] })
    },
  })
}
