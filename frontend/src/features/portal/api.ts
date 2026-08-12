// Phase 4 포털 데이터 훅 — 내부 api/tokenStore 재사용, queryKey 접두어 ['portal', ...]
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import { unwrapList } from '../../lib/api/queries'
import type {
  PortalMe,
  PortalProjectListItem,
  PortalProjectView,
  PortalTimelinePoint,
} from './types'

/** 로그인한 포털 사용자 정보 — PortalAuthProvider가 제공하는 me 재조회용 */
export function usePortalMe() {
  return useQuery({
    queryKey: ['portal', 'me'],
    queryFn: async () => {
      const { data } = await api.get<PortalMe>('/portal/me')
      return data
    },
    staleTime: 5 * 60_000,
  })
}

/** 참여 프로젝트 목록 */
export function usePortalProjects() {
  return useQuery({
    queryKey: ['portal', 'projects'],
    queryFn: async () => {
      const { data } = await api.get<PortalProjectListItem[]>('/portal/projects')
      return unwrapList(data).items
    },
  })
}

/** 프로젝트 상세 — 역할별 union(PARTNER/INVESTOR) */
export function usePortalProject(projectId: string | undefined) {
  return useQuery({
    queryKey: ['portal', 'projects', projectId],
    queryFn: async () => {
      const { data } = await api.get<PortalProjectView>(`/portal/projects/${projectId}`)
      return data
    },
    enabled: !!projectId,
  })
}

/** 프로젝트 시계열(감축량·수혜금액) — INVESTOR는 expected_payout 미포함 */
export function usePortalTimeline(projectId: string | undefined) {
  return useQuery({
    queryKey: ['portal', 'projects', projectId, 'timeline'],
    queryFn: async () => {
      const { data } = await api.get<PortalTimelinePoint[]>(
        `/portal/projects/${projectId}/timeline`,
      )
      return data ?? []
    },
    enabled: !!projectId,
  })
}
