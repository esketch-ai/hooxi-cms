// SCR-06 감축 사업 API 훅 — backend/routers/projects.py 계약 준수
// (상세 GET /projects/{id}가 clients 매핑·allocation_total을 함께 반환)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import { unwrapList } from '../../lib/api/queries'
import type {
  MappingPayload,
  Paginated,
  Project,
  ProjectClientMap,
  ProjectPayload,
  ProjectStage,
  ProjectStageAlerts,
  ProjectVehicle,
  ProjectVehicleList,
  ProjectVehiclePayload,
} from '../../types'

export interface ProjectFilters {
  project_status?: string
  manager_id?: string
  mon_cycle?: string
  search?: string
  page: number
  page_size: number
}

export function useProjects(filters: ProjectFilters) {
  return useQuery({
    queryKey: ['projects', 'list', filters],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page: filters.page,
        page_size: filters.page_size,
      }
      if (filters.project_status) params.project_status = filters.project_status
      if (filters.manager_id) params.manager_id = filters.manager_id
      if (filters.mon_cycle) params.mon_cycle = filters.mon_cycle
      if (filters.search) params.search = filters.search
      const { data } = await api.get<Project[] | Paginated<Project>>('/projects', { params })
      return unwrapList(data)
    },
  })
}

/** 셀렉트 옵션·대표사 판정용 전체 사업 목록 (SCR-07 필터 공용) */
export function useProjectOptions() {
  return useQuery({
    queryKey: ['projects', 'options'],
    queryFn: async () => {
      const { data } = await api.get<Project[] | Paginated<Project>>('/projects', {
        params: { page_size: 200 },
      })
      return unwrapList(data).items
    },
    staleTime: 60_000,
  })
}

/** 사업 상세 (ProjectDetailOut) — 개요 + clients 매핑 + allocation_total */
export function useProject(projectId: string | undefined) {
  return useQuery({
    queryKey: ['projects', projectId],
    queryFn: async () => {
      const { data } = await api.get<Project>(`/projects/${projectId}`)
      return data
    },
    enabled: !!projectId,
  })
}

/** 사업 참여 차량 목록 (Phase 2) */
export function useProjectVehicles(projectId: string | undefined) {
  return useQuery({
    queryKey: ['projects', projectId, 'vehicles'],
    queryFn: async () => {
      const { data } = await api.get<ProjectVehicleList>(`/projects/${projectId}/vehicles`)
      return data
    },
    enabled: !!projectId,
  })
}

/** 차량 등록/수정 (Phase 2) */
export function useSaveVehicle(projectId: string | undefined, vehicleId?: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: ProjectVehiclePayload) => {
      const { data } = vehicleId
        ? await api.put<ProjectVehicle>(`/projects/${projectId}/vehicles/${vehicleId}`, payload)
        : await api.post<ProjectVehicle>(`/projects/${projectId}/vehicles`, payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'vehicles'] })
      queryClient.invalidateQueries({ queryKey: ['projects', projectId] })
    },
  })
}

/** 차량 삭제 (Phase 2) */
export function useDeleteVehicle(projectId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (vehicleId: string) => {
      await api.delete(`/projects/${projectId}/vehicles/${vehicleId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'vehicles'] })
      queryClient.invalidateQueries({ queryKey: ['projects', projectId] })
    },
  })
}

/** 진행 단계 예정일/실제일 편집 (Phase 1) — 전달된 필드만 반영 */
export function useUpdateStages(projectId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (stages: Partial<ProjectStage>[]) => {
      const { data } = await api.put<Project>(`/projects/${projectId}/stages`, { stages })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}

/** 단계 지연/임박 관찰 (Phase 1 대시보드 위젯) */
export function useStageDelays() {
  return useQuery({
    queryKey: ['projects', 'stage-delays'],
    queryFn: async () => {
      const { data } = await api.get<ProjectStageAlerts>('/projects/stage-delays')
      return data
    },
  })
}

export function useSaveProject(projectId?: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: ProjectPayload) => {
      const { data } = projectId
        ? await api.put<Project>(`/projects/${projectId}`, payload)
        : await api.post<Project>('/projects', payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.invalidateQueries({ queryKey: ['settlements'] })
    },
  })
}

/** 배출권 단가 수기 입력 (§10.3) — 서버가 매핑 expected_amount 전체 재계산 */
export function useUpdateUnitPrice(projectId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (unitPrice: number | null) => {
      const { data } = await api.put<Project>(`/projects/${projectId}/unit-price`, {
        unit_price: unitPrice,
      })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.invalidateQueries({ queryKey: ['settlements'] })
    },
  })
}

/** 참여 고객사 매핑 등록/수정 — POST upsert(동일 고객사 갱신). 합계 100% 초과 시 서버 422 */
export function useSaveMapping(projectId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: MappingPayload) => {
      const { data } = await api.post<ProjectClientMap>(`/projects/${projectId}/clients`, payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.invalidateQueries({ queryKey: ['settlements'] })
    },
  })
}

export function useDeleteMapping(projectId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (mapId: string) => {
      await api.delete(`/projects/${projectId}/clients/${mapId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.invalidateQueries({ queryKey: ['settlements'] })
    },
  })
}

/** 사업 본체 삭제 — 정산 진행(BILLED/COMPLETED) 사업은 백엔드가 409로 막는다. */
export function useDeleteProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (projectId: string) => {
      await api.delete(`/projects/${projectId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.invalidateQueries({ queryKey: ['settlements'] })
    },
  })
}

/** D-day 임박 판정 — 예상 발급일 7일 이내·경과 시 빨강 (과업 기준) */
export function isIssueImminent(dd: { label: string; overdue: boolean } | null): boolean {
  if (!dd) return false
  if (dd.overdue || dd.label === 'D-DAY') return true
  const m = /^D-(\d+)$/.exec(dd.label)
  return !!m && Number(m[1]) <= 7
}

/** 진행 상태 — 백엔드 저장 값 그대로 한국어 (schemas._PROJECT_STATUS_PATTERN) */
export const PROJECT_STATUS_OPTIONS = [
  { value: '기획', label: '기획' },
  { value: '등록완료', label: '등록완료' },
  { value: '모니터링', label: '모니터링' },
  { value: '검증', label: '검증' },
  { value: '발급완료', label: '발급완료' },
]

export const MON_CYCLE_OPTIONS = [
  { value: '월간', label: '월간' },
  { value: '분기', label: '분기' },
  { value: '반기', label: '반기' },
  { value: '연간', label: '연간' },
]
