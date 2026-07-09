import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import type { TokenPair } from '../../types'

const ACCESS_KEY = 'hooxi_access_token'
const REFRESH_KEY = 'hooxi_refresh_token'

export const tokenStore = {
  getAccess: () => localStorage.getItem(ACCESS_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  set: (tokens: TokenPair) => {
    localStorage.setItem(ACCESS_KEY, tokens.access_token)
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token)
  },
  clear: () => {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

export const api = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
})

api.interceptors.request.use((config) => {
  const token = tokenStore.getAccess()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── 401 → refresh 후 원 요청 1회 재시도 ──────────────────────────────
type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean }

let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const refresh = tokenStore.getRefresh()
  if (!refresh) throw new Error('no refresh token')
  // 인터셉터 루프 방지를 위해 별도 인스턴스 사용
  const { data } = await axios.post<TokenPair>('/api/v1/auth/refresh', {
    refresh_token: refresh,
  })
  tokenStore.set(data)
  return data.access_token
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetriableConfig | undefined
    const status = error.response?.status
    const url = config?.url ?? ''

    const isAuthEndpoint =
      url.includes('/auth/refresh') ||
      url.includes('/auth/dev-login') ||
      url.includes('/auth/works/')

    if (status === 401 && config && !config._retried && !isAuthEndpoint) {
      config._retried = true
      try {
        refreshPromise = refreshPromise ?? refreshAccessToken()
        const newAccess = await refreshPromise
        config.headers.Authorization = `Bearer ${newAccess}`
        return api(config)
      } catch (refreshError) {
        tokenStore.clear()
        window.dispatchEvent(new CustomEvent('auth:logout'))
        return Promise.reject(refreshError)
      } finally {
        refreshPromise = null
      }
    }

    return Promise.reject(error)
  },
)
