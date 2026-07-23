// 수집 계정 관리 API 훅 — GET /assets?credentials_only=true (로그인 계정 보유 자산만)
// + POST /batch/account-check (ADMIN 수동 전체 점검). reveal은 assets/useRevealAuth 재사용.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import { unwrapList } from '../../lib/api/queries'
import type { AccountCheckResponse, AccountCheckSummary, Asset, Paginated } from '../../types'

export interface AccountFilters {
  /** 대분류 MOBILITY/FACILITY */
  asset_category?: string
  /** 인증 방식 API_KEY/ID_PW */
  auth_method?: string
  /** 고객사명 검색 */
  search?: string
  /** 점검 상태 필터 pending/done/issue (계정 관리 뷰) */
  check_state?: string
  page: number
  page_size: number
}

/** 로그인 계정 보유 자산 목록 — credentials_only로 백엔드가 auth_type != NONE만 반환.
 *  응답에 자산별 이번 달 점검 상태(check_status)와 상단 요약(check_summary) 포함. */
export function useCredentialAssets(filters: AccountFilters) {
  return useQuery({
    queryKey: ['accounts', filters],
    queryFn: async () => {
      const params: Record<string, string | number | boolean> = {
        credentials_only: true,
        page: filters.page,
        page_size: filters.page_size,
      }
      if (filters.asset_category) params.asset_category = filters.asset_category
      if (filters.auth_method) params.auth_method = filters.auth_method
      if (filters.search) params.search = filters.search
      if (filters.check_state) params.check_state = filters.check_state
      const { data } = await api.get<Asset[] | Paginated<Asset>>('/assets', { params })
      const list = unwrapList(data)
      const check_summary =
        !Array.isArray(data) && data
          ? (data as { check_summary?: AccountCheckSummary }).check_summary
          : undefined
      return { ...list, check_summary }
    },
  })
}

/** 전체 계정 월별 점검 실행 (ADMIN) — 대상 자산별 점검 이슈 생성(멱등)
 *  사이트 도달성 확인(병렬)으로 수십 초 걸릴 수 있어 기본 15초 대신 전용 타임아웃 사용 */
export function useAccountCheck() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<AccountCheckResponse>('/batch/account-check', null, {
        timeout: 120_000,
      })
      return data
    },
    onSuccess: () => {
      // 점검 이슈가 생성됨 — 이슈 보드·활동 이력·현황판이 바로 반영되도록 무효화
      queryClient.invalidateQueries({ queryKey: ['issues'] })
      queryClient.invalidateQueries({ queryKey: ['histories'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}
