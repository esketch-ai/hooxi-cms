// 공용 서버 상태 훅 — 여러 화면에서 재사용하는 셀렉트 옵션(고객사·사용자) 등
import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import type { Client, Paginated, User } from '../../types'

/** 배열/Paginated 어느 쪽이 와도 items·total로 정규화 */
export function unwrapList<T>(data: T[] | Paginated<T> | null | undefined): {
  items: T[]
  total: number
} {
  if (!data) return { items: [], total: 0 }
  if (Array.isArray(data)) return { items: data, total: data.length }
  return { items: data.items ?? [], total: data.total ?? data.items?.length ?? 0 }
}

/** 고객사 셀렉트 옵션용 전체 목록 (폼·필터 공용) */
export function useClientOptions() {
  return useQuery({
    queryKey: ['clients', 'options'],
    queryFn: async () => {
      const { data } = await api.get<Client[] | Paginated<Client>>('/clients', {
        params: { page_size: 200 },
      })
      return unwrapList(data).items
    },
    staleTime: 60_000,
  })
}

/** 사용자(담당 PM·작성자) 셀렉트 옵션 — MANAGER 미만 403이면 빈 목록 폴백 */
export function useUserOptions() {
  return useQuery({
    queryKey: ['users', 'options'],
    queryFn: async () => {
      try {
        const { data } = await api.get<User[]>('/users', { params: { status: 'ACTIVE' } })
        return data
      } catch {
        return [] as User[]
      }
    },
    staleTime: 300_000,
  })
}
