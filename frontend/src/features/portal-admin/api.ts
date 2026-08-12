// INC-8b 외부 포털 계정 관리 API 훅 — 백엔드 /external-accounts (전부 MANAGER↑ 전용)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import type { UserStatus } from '../../types'

/** 외부 포털 역할 — PARTNER=운수사 / INVESTOR=투자·금융사 */
export type ExternalRole = 'PARTNER' | 'INVESTOR'

/** 발급/재발급 응답 — magic_link 포함 (목록 응답에서는 null) */
export interface ExternalAccount {
  user_id: string
  email: string
  name?: string | null
  role: ExternalRole
  client_id?: string | null
  buyer_id?: string | null
  status: UserStatus
  magic_link?: string | null
}

/** 계정 발급 payload (schemas.ExternalAccountIn) */
export interface ExternalAccountIn {
  email: string
  name?: string | null
  role: ExternalRole
  client_id?: string | null // PARTNER 필수 (운수사)
  buyer_id?: string | null // INVESTOR 필수 (매수자)
  kakao_contact_id?: string | null
}

export function useExternalAccounts(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['external-accounts'],
    queryFn: async () => {
      const { data } = await api.get<ExternalAccount[]>('/external-accounts')
      return data
    },
    // MANAGER↑ 전용 엔드포인트 — 비인가 역할이 직접 진입 시 403 반복요청 방지
    enabled: options?.enabled ?? true,
  })
}

export function useCreateExternalAccount() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: ExternalAccountIn) => {
      const { data } = await api.post<ExternalAccount>('/external-accounts', payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['external-accounts'] })
    },
  })
}

export function useResendMagicLink() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (userId: string) => {
      const { data } = await api.post<ExternalAccount>(
        `/external-accounts/${userId}/resend-link`,
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['external-accounts'] })
    },
  })
}

export function useDeactivateExternalAccount() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (userId: string) => {
      const { data } = await api.delete<ExternalAccount>(`/external-accounts/${userId}`)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['external-accounts'] })
    },
  })
}

/** 매직링크 절대 URL 구성 — Dev에선 상대경로(/portal/login?token=...)로 올 수 있음 */
export function absoluteMagicLink(link?: string | null): string {
  if (!link) return ''
  return link.startsWith('http') ? link : window.location.origin + link
}
