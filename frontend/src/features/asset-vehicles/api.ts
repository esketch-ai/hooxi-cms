// AV-3 전기버스 자산 API 훅 — backend GET /asset-vehicles 계약 준수
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import type { AssetVehicleFilters, AssetVehicleListResponse } from './types'

export function useAssetVehicles(filters: AssetVehicleFilters) {
  return useQuery({
    queryKey: ['asset-vehicles', filters],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page: filters.page,
        page_size: filters.page_size,
      }
      if (filters.project_id) params.project_id = filters.project_id
      if (filters.region) params.region = filters.region
      if (filters.client_id) params.client_id = filters.client_id
      if (filters.approval_status) params.approval_status = filters.approval_status
      if (filters.buyer_id) params.buyer_id = filters.buyer_id
      if (filters.registered_from) params.registered_from = filters.registered_from
      if (filters.registered_to) params.registered_to = filters.registered_to
      if (filters.expire_before) params.expire_before = filters.expire_before
      if (filters.search) params.search = filters.search
      const { data } = await api.get<AssetVehicleListResponse>('/asset-vehicles', { params })
      return data
    },
    placeholderData: (prev) => prev, // 페이지·필터 전환 시 이전 결과 유지(깜빡임 방지)
  })
}
