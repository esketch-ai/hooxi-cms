// 공용 서버 상태 훅 — 여러 화면에서 재사용하는 셀렉트 옵션(고객사·사용자) 등
import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import type { ChatBadge, Client, Paginated, User } from '../../types'

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

/** 카카오 상담 LNB 뱃지 — GET /chat/badge 15초 폴링 (Sidebar·BottomNav 공용) */
export function useChatBadge() {
  return useQuery({
    queryKey: ['chat', 'badge'],
    queryFn: async () => {
      try {
        const { data } = await api.get<ChatBadge>('/chat/badge')
        return { waiting: data?.waiting ?? 0 }
      } catch {
        // 백엔드 미배포·미설정 시 뱃지 숨김 (콘솔 에러 폴링 방지)
        return { waiting: 0 }
      }
    },
    refetchInterval: 15_000,
    staleTime: 10_000,
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
