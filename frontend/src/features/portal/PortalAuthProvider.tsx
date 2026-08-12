// Phase 4 포털 전용 인증 컨텍스트 — 내부 AuthProvider와 완전 분리(격리).
// 내부 api/tokenStore(같은 localStorage 키)를 재사용하되, 포털 서브트리에서만 usePortalAuth로 소비.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api, tokenStore } from '../../lib/api/client'
import type { TokenPair } from '../../types'
import type { PortalMe } from './types'

interface PortalAuthValue {
  me: PortalMe | null
  isLoading: boolean
  isError: boolean
  /** 매직 토큰 검증 → 토큰 저장 → me 조회 */
  verifyMagic: (token: string) => Promise<PortalMe>
  logout: () => void
}

const PortalAuthContext = createContext<PortalAuthValue | null>(null)

export function PortalAuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<PortalMe | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isError, setIsError] = useState(false)
  const queryClient = useQueryClient()

  const fetchMe = useCallback(async (): Promise<PortalMe | null> => {
    if (!tokenStore.getAccess()) {
      setMe(null)
      return null
    }
    try {
      const { data } = await api.get<PortalMe>('/portal/me')
      setMe(data)
      setIsError(false)
      return data
    } catch {
      // 401/403 등 → 로그인 필요(me=null). 토큰이 내부용일 수도 있으므로 여기서 clear하지 않음.
      setMe(null)
      return null
    }
  }, [])

  useEffect(() => {
    fetchMe().finally(() => setIsLoading(false))
  }, [fetchMe])

  const verifyMagic = useCallback(
    async (token: string): Promise<PortalMe> => {
      setIsError(false)
      try {
        const { data } = await api.post<TokenPair>('/portal/auth/verify', { token })
        // 이전 계정의 포털 캐시 잔존 방지(계정 전환 시 순간 노출 차단)
        queryClient.removeQueries({ queryKey: ['portal'] })
        tokenStore.set(data)
        const next = await fetchMe()
        if (!next) throw new Error('포털 사용자 정보를 불러오지 못했습니다')
        return next
      } catch (error) {
        setIsError(true)
        throw error
      }
    },
    [fetchMe, queryClient],
  )

  const logout = useCallback(() => {
    tokenStore.clear()
    setMe(null)
    queryClient.removeQueries({ queryKey: ['portal'] })
  }, [queryClient])

  const value = useMemo<PortalAuthValue>(
    () => ({ me, isLoading, isError, verifyMagic, logout }),
    [me, isLoading, isError, verifyMagic, logout],
  )

  return <PortalAuthContext.Provider value={value}>{children}</PortalAuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function usePortalAuth(): PortalAuthValue {
  const ctx = useContext(PortalAuthContext)
  if (!ctx) throw new Error('usePortalAuth must be used within PortalAuthProvider')
  return ctx
}
