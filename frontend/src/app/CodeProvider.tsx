// 공통 코드 전역 캐시 — StatusBadge 같은 동기 컴포넌트가 코드값→표시명/색상을
// 훅 없이 조회할 수 있도록 앱 시작 시 관리 카테고리를 1회 로드해 Context로 제공한다.
import { createContext, useCallback, useContext, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api/client'
import { useAuth } from './AuthProvider'
import type { Code } from '../types'

// StatusBadge 등에서 마스터 기반으로 렌더할 카테고리 (Phase 1+2 범위)
const MANAGED_CATEGORIES = [
  'CLIENT_TYPE',
  'CONTRACT_STATUS',
  'ACTIVITY_TYPE',
  'ASSET_GROUP',
  'ASSET_TYPE',
  'ASSET_STATUS',
  'PROJECT_STATUS',
  'SETTLEMENT_STATUS',
  'ISSUE_STATUS',
] as const

export interface CodeInfo {
  label: string
  color?: string | null
}
type CodeMap = Record<string, Record<string, CodeInfo>>

const CodeContext = createContext<(category: string, code?: string | null) => CodeInfo | undefined>(
  () => undefined,
)

export function CodeProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth()

  // queryKey가 ['codes', ...]라 CodesTab의 invalidateQueries(['codes'])로 함께 갱신됨
  const { data } = useQuery({
    queryKey: ['codes', '_provider'],
    enabled: isAuthenticated,
    staleTime: 5 * 60_000,
    queryFn: async () => {
      const entries = await Promise.all(
        MANAGED_CATEGORIES.map(async (category) => {
          const { data } = await api.get<Code[]>('/codes', {
            params: { category, include_inactive: true },
          })
          return [category, data] as const
        }),
      )
      const map: CodeMap = {}
      for (const [category, codes] of entries) {
        map[category] = {}
        for (const c of codes) map[category][c.code] = { label: c.label, color: c.color }
      }
      return map
    },
  })

  const lookup = useCallback(
    (category: string, code?: string | null): CodeInfo | undefined =>
      code ? data?.[category]?.[code] : undefined,
    [data],
  )

  return <CodeContext.Provider value={lookup}>{children}</CodeContext.Provider>
}

/** 코드값→{label,color} 동기 조회 (없으면 undefined → 호출부에서 폴백) */
export function useCodeLookup() {
  return useContext(CodeContext)
}
