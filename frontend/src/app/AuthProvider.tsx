import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api, tokenStore } from '../lib/api/client'
import type { TokenPair, User } from '../types'

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
  /** 이메일+PIN 로그인 (POST /auth/email-login) — 회사 도메인 제한 */
  loginEmail: (
    email: string,
    pin?: string,
  ) => Promise<{ status: 'OK' | 'PIN_REQUIRED' | 'PENDING'; me?: User }>
  /** PIN 설정 (POST /auth/pin) */
  setPin: (pin: string) => Promise<void>
  logout: () => void
  refetchMe: () => Promise<User | null>
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

  const loginEmail = useCallback(
    async (
      email: string,
      pin?: string,
    ): Promise<{ status: 'OK' | 'PIN_REQUIRED' | 'PENDING'; me?: User }> => {
      const { data } = await api.post('/auth/email-login', { email, pin })
      if (data.status === 'OK' && data.access_token && data.refresh_token) {
        tokenStore.set({
          access_token: data.access_token,
          refresh_token: data.refresh_token,
        })
        const me = await fetchMe()
        if (!me) throw new Error('사용자 정보를 불러오지 못했습니다')
        return { status: 'OK', me }
      }
      if (data.status === 'PENDING') {
        // 승인 대기 화면 표시용 유저 상태 (토큰 없음)
        setUser({
          user_id: '',
          email: email.trim().toLowerCase(),
          name: '',
          role: 'STAFF',
          status: 'PENDING',
          pin_set: false,
        } as User)
        return { status: 'PENDING' }
      }
      return { status: 'PIN_REQUIRED' }
    },
    [fetchMe],
  )

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
      loginEmail,
      setPin,
      logout,
      refetchMe: fetchMe,
    }),
    [user, isLoading, loginDev, loginEmail, setPin, logout, fetchMe],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
