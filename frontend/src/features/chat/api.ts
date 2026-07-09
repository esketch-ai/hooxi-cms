// SCR-08 카카오톡 상담 관제 API 훅 — 플랜(nifty-conjuring-turtle) API 계약 기준
// GET /chat/threads · GET /chat/threads/{id}/messages?after= · POST /chat/threads/{id}/reply
// PUT /chat/threads/{id} · GET /chat/badge · GET/PUT /kakao/contacts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { api } from '../../lib/api/client'
import { unwrapList } from '../../lib/api/queries'
import type {
  ChatMessage,
  ChatMode,
  ChatReplyResponse,
  ChatThread,
  ChatThreadStatus,
  KakaoContact,
  Paginated,
} from '../../types'

/** 스레드 폴링 간격 (플랜: TanStack Query refetchInterval 5초) */
const POLL_MS = 5_000

function sortByLastMessage(items: ChatThread[]): ChatThread[] {
  return [...items].sort((a, b) =>
    (b.last_message_at ?? b.updated_at ?? '').localeCompare(a.last_message_at ?? a.updated_at ?? ''),
  )
}

/** 스레드 리스트 — 검색 + 5초 폴링 (last_message_at 역순) */
export function useChatThreads(search: string) {
  return useQuery({
    queryKey: ['chat', 'threads', 'list', search],
    queryFn: async () => {
      const params: Record<string, string> = {}
      if (search) params.search = search
      const { data } = await api.get<ChatThread[] | Paginated<ChatThread>>('/chat/threads', {
        params,
      })
      return sortByLastMessage(unwrapList(data).items)
    },
    refetchInterval: POLL_MS,
    placeholderData: (prev) => prev,
  })
}

/** 고객사 상세(SCR-03D) 상담 탭 — 해당 고객사 스레드 목록 */
export function useClientThreads(clientId: string | undefined) {
  return useQuery({
    queryKey: ['chat', 'threads', 'client', clientId],
    queryFn: async () => {
      const { data } = await api.get<ChatThread[] | Paginated<ChatThread>>('/chat/threads', {
        params: { client_id: clientId },
      })
      // 백엔드가 client_id 파라미터를 지원하지 않아도 안전하도록 재필터
      return sortByLastMessage(
        unwrapList(data).items.filter((t) => t.client_id === clientId),
      )
    },
    enabled: !!clientId,
  })
}

/**
 * 선택 스레드 메시지 — 5초 폴링 + after= 증분 조회.
 * 캐시에 쌓인 마지막 message_id를 after로 보내고 신규분만 병합한다.
 * 백엔드가 after를 무시하고 전체를 반환해도 message_id 중복 제거로 안전.
 */
export function useChatMessages(threadId: string | undefined) {
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: ['chat', 'messages', threadId],
    queryFn: async () => {
      const cacheKey = ['chat', 'messages', threadId]
      const prev = queryClient.getQueryData<ChatMessage[]>(cacheKey)
      const after = prev && prev.length > 0 ? prev[prev.length - 1].message_id : undefined
      const fetchMessages = async (afterId?: string) => {
        const { data } = await api.get<ChatMessage[] | Paginated<ChatMessage>>(
          `/chat/threads/${threadId}/messages`,
          { params: afterId ? { after: afterId } : {} },
        )
        return unwrapList(data).items
      }
      let items: ChatMessage[]
      try {
        items = await fetchMessages(after)
      } catch (err) {
        // 기준 메시지(after) 소실 시 백엔드가 404 — 전체 재조회 폴백
        if (after && isAxiosError(err) && err.response?.status === 404) {
          return fetchMessages()
        }
        throw err
      }
      if (!prev || !after) return items
      const known = new Set(prev.map((m) => m.message_id))
      const fresh = items.filter((m) => !known.has(m.message_id))
      return fresh.length > 0 ? [...prev, ...fresh] : prev
    },
    enabled: !!threadId,
    refetchInterval: POLL_MS,
  })
}

/** 직원 답변 — POST reply → {delivery: SENT|FAILED|NOT_CONFIGURED} */
export function useReplyThread(threadId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (content: string) => {
      const { data } = await api.post<ChatReplyResponse>(
        `/chat/threads/${threadId}/reply`,
        { content },
        { timeout: 30_000 },
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat', 'messages', threadId] })
      queryClient.invalidateQueries({ queryKey: ['chat', 'threads'] })
      queryClient.invalidateQueries({ queryKey: ['chat', 'badge'] })
    },
  })
}

export interface ThreadUpdatePayload {
  mode?: ChatMode
  status?: ChatThreadStatus
  assigned_manager_id?: string | null
}

/** 모드 전환(AI↔직원)·담당 배정·상담 종료 — PUT /chat/threads/{id} */
export function useUpdateThread(threadId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: ThreadUpdatePayload) => {
      const { data } = await api.put<ChatThread>(`/chat/threads/${threadId}`, payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chat', 'threads'] })
      queryClient.invalidateQueries({ queryKey: ['chat', 'messages', threadId] })
      queryClient.invalidateQueries({ queryKey: ['chat', 'badge'] })
      // 종료 시 활동 이력(KAKAO [자동]) 적재 반영
      queryClient.invalidateQueries({ queryKey: ['histories'] })
    },
  })
}

/** 승인 대기 연락처 목록 — GET /kakao/contacts?status=PENDING (15초 폴링) */
export function usePendingContacts() {
  return useQuery({
    queryKey: ['kakao', 'contacts', 'PENDING'],
    queryFn: async () => {
      try {
        const { data } = await api.get<KakaoContact[] | Paginated<KakaoContact>>(
          '/kakao/contacts',
          { params: { status: 'PENDING' } },
        )
        return unwrapList(data).items
      } catch {
        // 백엔드 미배포 시 빈 목록 폴백
        return [] as KakaoContact[]
      }
    },
    refetchInterval: 15_000,
  })
}

export interface ContactUpdatePayload {
  contactId: string
  status: 'APPROVED' | 'REJECTED' | 'BLOCKED'
  client_id?: string | null
}

/** 연락처 승인(고객사 매핑 확정)·거절 — PUT /kakao/contacts/{id} (MANAGER 이상) */
export function useUpdateKakaoContact() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ contactId, status, client_id }: ContactUpdatePayload) => {
      const { data } = await api.put<KakaoContact>(`/kakao/contacts/${contactId}`, {
        status,
        ...(client_id ? { client_id } : {}),
      })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kakao', 'contacts'] })
      queryClient.invalidateQueries({ queryKey: ['chat', 'threads'] })
    },
  })
}
