// SCR-04 자산 및 연동 현황 API 훅 — backend/routers/assets.py 계약 준수
// (쿼리 파라미터: asset_category / monitoring_yn / auth_method / client_id / search)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import { unwrapList } from '../../lib/api/queries'
import type { Asset, AssetPayload, Paginated } from '../../types'

export interface AssetFilters {
  asset_category?: string
  monitoring_yn?: string
  auth_method?: string
  search?: string
  page: number
  page_size: number
}

export function useAssets(filters: AssetFilters) {
  return useQuery({
    queryKey: ['assets', filters],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page: filters.page,
        page_size: filters.page_size,
      }
      if (filters.asset_category) params.asset_category = filters.asset_category
      if (filters.monitoring_yn) params.monitoring_yn = filters.monitoring_yn
      if (filters.auth_method) params.auth_method = filters.auth_method
      if (filters.search) params.search = filters.search
      const { data } = await api.get<Asset[] | Paginated<Asset>>('/assets', { params })
      return unwrapList(data)
    },
  })
}

export function useSaveAsset(assetId?: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: AssetPayload) => {
      const { data } = assetId
        ? await api.put<Asset>(`/assets/${assetId}`, payload)
        : await api.post<Asset>('/assets', payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['assets'] })
    },
  })
}

export function useDeleteAsset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (assetId: string) => {
      await api.delete(`/assets/${assetId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['assets'] })
    },
  })
}
