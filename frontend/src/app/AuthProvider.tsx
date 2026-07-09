import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { isAxiosError } from 'axios'
import { api, tokenStore } from '../lib/api/client'
import type { AuthorizeResponse, TokenPair, User } from '../types'

interface AuthContextValue {
  user: User | null
  /** 초기 me 조회 진행 중 */
  isLoading: boolean
  /** ACTIVE 사용자로 인증됨 */
  isAuthenticated: boolean
  /** 가입 승인 대기(PENDING) */
  isPending: boolean
  /** PIN 설정 여부 (미팅 모드·reveal 게이트용, R2-C11) */
  pinSet: boolean
  /** 개발용 로그인 (POST /auth/dev-login) — DEV 전용 */
  loginDev: (email: string) => Promise<User>
  /** 네이버웍스 SSO — authorize URL로 리다이렉트. 501이면 NotImplemented 에러 */
  loginWithWorks: () => Promise<void>
  /** PIN 설정 (POST /auth/pin) */
  setPin: (pin: string) => Promise<void>
  logout: () => void
  refetchMe: () => Promise<User | null>
}

export class WorksNotReadyError extends Error {
  constructor() {
    super('네이버웍스 연동 준비 중입니다')
    this.name = 'WorksNotReadyError'
  }
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const fetchMe = useCallback(async (): Promise<User | null> => {
    if (!tokenStore.getAccess()) {
      setUser(null)
      return null
    }
    try {
      const { data } = await api.get<User>('/users/me')
      setUser(data)
      return data
    } catch {
      setUser(null)
      return null
    }
  }, [])

  useEffect(() => {
    fetchMe().finally(() => setIsLoading(false))
  }, [fetchMe])

  // 토큰 갱신 실패 등으로 강제 로그아웃 (client.ts에서 발생)
  useEffect(() => {
    const onForcedLogout = () => setUser(null)
    window.addEventListener('auth:logout', onForcedLogout)
    return () => window.removeEventListener('auth:logout', onForcedLogout)
  }, [])

  const loginDev = useCallback(
    async (email: string): Promise<User> => {
      const { data } = await api.post<TokenPair>('/auth/dev-login', { email })
      tokenStore.set(data)
      const me = await fetchMe()
      if (!me) throw new Error('사용자 정보를 불러오지 못했습니다')
      return me
    },
    [fetchMe],
  )

  const loginWithWorks = useCallback(async () => {
    try {
      const { data } = await api.get<AuthorizeResponse>('/auth/works/authorize')
      const authorizeUrl = data?.authorize_url ?? data?.url
      if (!authorizeUrl) throw new WorksNotReadyError()
      window.location.href = authorizeUrl
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 501) {
        throw new WorksNotReadyError()
      }
      throw error
    }
  }, [])

  const setPin = useCallback(async (pin: string) => {
    await api.post('/auth/pin', { pin })
    setUser((prev) => (prev ? { ...prev, pin_set: true } : prev))
  }, [])

  const logout = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isLoading,
      isAuthenticated: !!user && user.status === 'ACTIVE',
      isPending: !!user && user.status === 'PENDING',
      pinSet: !!user?.pin_set,
      loginDev,
      loginWithWorks,
      setPin,
      logout,
      refetchMe: fetchMe,
    }),
    [user, isLoading, loginDev, loginWithWorks, setPin, logout, fetchMe],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
