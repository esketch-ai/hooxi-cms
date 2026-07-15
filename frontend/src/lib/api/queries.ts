// 공용 서버 상태 훅 — 여러 화면에서 재사용하는 셀렉트 옵션(고객사·사용자) 등
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import type { ChatBadge, Client, Code, Document, Paginated, User } from '../../types'

/**
 * 공통 코드 마스터 조회 (tb_code). 드롭다운 옵션 + 코드값→표시명 매핑을 함께 제공.
 * - options: 활성 코드만 (신규 선택지용)
 * - labelOf(code): 표시명 반환, 없으면 코드값 원문(구분 삭제/변동 시에도 오표시 방지)
 * include_inactive=true로 전체를 받아 비활성 코드도 라벨 해석은 되게 한다.
 */
export function useCodes(category: string) {
  const query = useQuery({
    queryKey: ['codes', category],
    queryFn: async () => {
      const { data } = await api.get<Code[]>('/codes', {
        params: { category, include_inactive: true },
      })
      return data
    },
    staleTime: 5 * 60_000,
  })

  const codes = query.data ?? []
  const labelMap = useMemo(() => {
    const m: Record<string, string> = {}
    for (const c of codes) m[c.code] = c.label
    return m
  }, [codes])

  const options = useMemo(
    () =>
      codes
        .filter((c) => c.active === 'Y')
        .map((c) => ({ value: c.code, label: c.label })),
    [codes],
  )

  const labelOf = (code?: string | null) => (code ? labelMap[code] ?? code : '')

  return { ...query, codes, options, labelOf }
}

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

/** 활동 이력 첨부 문서 목록 — GET /documents?history_id= (SCR-05 확장 행 등) */
export function useHistoryDocuments(historyId: string | null | undefined) {
  return useQuery({
    queryKey: ['documents', 'history', historyId],
    queryFn: async () => {
      const { data } = await api.get<Document[] | Paginated<Document>>('/documents', {
        params: { history_id: historyId, page_size: 100 },
      })
      return unwrapList(data).items
    },
    enabled: !!historyId,
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
