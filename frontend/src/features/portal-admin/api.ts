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
  phone?: string | null
  portal_expires_at?: string | null // 이용권 만료(만료 후 로그인 차단)
  magic_link?: string | null
  /** 카카오 알림톡 발송 결과 (발급·재발급 응답에만 존재, 목록은 없음) */
  delivery?: string | null
}

/** 계정 발급 payload (schemas.ExternalAccountIn) */
export interface ExternalAccountIn {
  email: string
  name?: string | null
  role: ExternalRole
  client_id?: string | null // PARTNER 필수 (운수사)
  buyer_id?: string | null // INVESTOR 필수 (매수자)
  phone?: string // 카카오 알림톡 발송용 (선택)
  kakao_contact_id?: string | null
  duration?: PassDuration // 이용권: 1d(1일권)/7d(1주권)/30d(1개월권)/365d(연간권)
}

/** 이용권 기간 — 링크 유효기간 = 이용권 기간, 만료 후 포털 로그인 차단 */
export type PassDuration = '1d' | '7d' | '30d' | '365d'
export const PASS_OPTIONS: { value: PassDuration; label: string }[] = [
  { value: '1d', label: '1일권' },
  { value: '7d', label: '1주권' },
  { value: '30d', label: '1개월권' },
  { value: '365d', label: '연간권' },
]

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
    mutationFn: async ({ userId, duration }: { userId: string; duration: PassDuration }) => {
      const { data } = await api.post<ExternalAccount>(
        `/external-accounts/${userId}/resend-link`,
        { duration },
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

// ── 발급 전 미리보기 — 이 계정이 포털에서 보게 될 내용(read-only, PORTAL_PREVIEW 감사) ──
import type { PortalFleetItem, PortalReportItem, PortalSettlementItem } from '../portal/types'

export interface ExternalAccountPreview {
  user_id: string
  name?: string | null
  email: string
  role: string
  status: string
  org_name?: string | null
  projects: { project_id: string; project_name: string; project_status?: string | null }[]
  fleet_status: PortalFleetItem[]
  reports: PortalReportItem[]
  settlements: PortalSettlementItem[]
  warnings: string[]
}

export function usePreviewExternalAccount() {
  return useMutation({
    mutationFn: async (userId: string) => {
      const { data } = await api.get<ExternalAccountPreview>(
        `/external-accounts/${userId}/preview`,
      )
      return data
    },
  })
}
