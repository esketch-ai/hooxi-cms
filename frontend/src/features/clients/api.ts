// SCR-03·03D API 훅 — 플랜 §5 엔드포인트 기준
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import { unwrapList } from '../../lib/api/queries'
import { downloadExport } from '../../lib/export'
import type {
  ActivityHistory,
  Asset,
  Client,
  ClientPayload,
  ClientVehicle,
  ClientVehicleList,
  ClientVehiclePayload,
  Document,
  FleetClientStatus,
  FleetImportResult,
  FleetMgmt,
  FleetPreviewResult,
  FleetStatusCommitResult,
  FleetStatusPreviewResult,
  Paginated,
  ReportDelivery,
  ReportRecipient,
} from '../../types'

export interface ClientFilters {
  client_type?: string
  contract_status?: string
  manager_id?: string
  search?: string
  page: number
  page_size: number
}

export function useClients(filters: ClientFilters) {
  return useQuery({
    queryKey: ['clients', filters],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page: filters.page,
        page_size: filters.page_size,
      }
      if (filters.client_type) params.client_type = filters.client_type
      if (filters.contract_status) params.contract_status = filters.contract_status
      if (filters.manager_id) params.manager_id = filters.manager_id
      if (filters.search) params.search = filters.search
      const { data } = await api.get<Client[] | Paginated<Client>>('/clients', { params })
      return unwrapList(data)
    },
  })
}

export function useClient(clientId: string | undefined) {
  return useQuery({
    queryKey: ['clients', clientId],
    queryFn: async () => {
      const { data } = await api.get<Client>(`/clients/${clientId}`)
      return data
    },
    enabled: !!clientId,
  })
}

export function useSaveClient(clientId?: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: ClientPayload) => {
      const { data } = clientId
        ? await api.put<Client>(`/clients/${clientId}`, payload)
        : await api.post<Client>('/clients', payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
    },
  })
}

/** 고객사 삭제 — 종속 없으면 바로 삭제(있으면 409). force+confirmName(담당자 본인 이름)으로
 *  종속까지 강제 삭제(단 사업/정산 있으면 백엔드가 강제여도 409). */
export function useDeleteClient() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (args: { clientId: string; force?: boolean; confirmName?: string }) => {
      const p = new URLSearchParams()
      if (args.force) {
        p.set('force', 'true')
        if (args.confirmName) p.set('confirm_name', args.confirmName)
      }
      const qs = p.toString()
      await api.delete(`/clients/${args.clientId}${qs ? `?${qs}` : ''}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
    },
  })
}

// ── 상세 탭 데이터 ──────────────────────────────────────────────────
export function useClientHistories(clientId: string | undefined) {
  return useQuery({
    queryKey: ['clients', clientId, 'histories'],
    queryFn: async () => {
      const { data } = await api.get<ActivityHistory[] | Paginated<ActivityHistory>>(
        `/clients/${clientId}/histories`,
      )
      return unwrapList(data).items
    },
    enabled: !!clientId,
  })
}

export function useClientReports(clientId: string | undefined) {
  return useQuery({
    queryKey: ['clients', clientId, 'reports'],
    queryFn: async () => {
      const { data } = await api.get<ReportDelivery[] | Paginated<ReportDelivery>>(
        `/clients/${clientId}/reports`,
      )
      return unwrapList(data).items
    },
    enabled: !!clientId,
  })
}

export function useClientDocuments(clientId: string | undefined) {
  return useQuery({
    queryKey: ['clients', clientId, 'documents'],
    queryFn: async () => {
      const { data } = await api.get<Document[] | Paginated<Document>>(
        `/clients/${clientId}/documents`,
      )
      return unwrapList(data).items
    },
    enabled: !!clientId,
  })
}

// ── 보고서 수신자 (tb_report_recipient, R2-B8) ──────────────────────
export function useClientRecipients(clientId: string | undefined) {
  return useQuery({
    queryKey: ['clients', clientId, 'recipients'],
    queryFn: async () => {
      const { data } = await api.get<ReportRecipient[]>(`/clients/${clientId}/recipients`)
      return data
    },
    enabled: !!clientId,
  })
}

export interface RecipientPayload {
  email: string
  name?: string
  cc_yn?: string // Y=CC / N=TO
  sub_id?: string // 미지정=전 유형 공통
}

export function useAddRecipient(clientId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: RecipientPayload) => {
      const { data } = await api.post<ReportRecipient>(
        `/clients/${clientId}/recipients`,
        payload,
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients', clientId, 'recipients'] })
    },
  })
}

export function useRemoveRecipient(clientId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (recipientId: string) => {
      const { data } = await api.delete(`/clients/${clientId}/recipients/${recipientId}`)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients', clientId, 'recipients'] })
    },
  })
}

export function useClientAssets(clientId: string | undefined) {
  return useQuery({
    queryKey: ['clients', clientId, 'assets'],
    queryFn: async () => {
      const { data } = await api.get<Asset[] | Paginated<Asset>>(`/clients/${clientId}/assets`)
      return unwrapList(data).items
    },
    enabled: !!clientId,
  })
}

// ── 감축 참여 라이프사이클 (참여상태 파생 + 3단계 감축량, P3) ────────
export interface ParticipationSummary {
  owned_count: number
  participating_count: number
  completed_count: number
  ongoing_count: number
  not_participated_count: number
  ev_candidate_count: number
  participation_rate: number | null
  expected_reduction_total: number
  monitoring_reduction_total: number
  final_reduction_total: number
}
export interface ParticipationVehicle {
  vehicle_no?: string | null
  introduction_type?: string | null
  participation_status: 'COMPLETED' | 'ONGOING'
  project_id?: string | null
  project_name?: string | null
  project_status?: string | null
  expected_reduction?: number | null
  monitoring_reduction?: number | null
  final_reduction?: number | null
  ach_monitoring?: number | null
  ach_final?: number | null
  expected_payout?: number | null
}
export interface NotParticipatedVehicle {
  vehicle_no?: string | null
  model_name?: string | null
  fuel?: string | null
  model_year?: number | null
  is_ev: boolean
}
export interface ClientParticipation {
  summary: ParticipationSummary
  participated: ParticipationVehicle[]
  not_participated: NotParticipatedVehicle[]
}
export function useClientParticipation(clientId: string | undefined) {
  return useQuery({
    queryKey: ['clients', clientId, 'participation'],
    queryFn: async () =>
      (await api.get<ClientParticipation>(`/clients/${clientId}/participation`)).data,
    enabled: !!clientId,
  })
}

// ── 보유 차량 (tb_client_vehicle, 부록 M) ───────────────────────────
export function useClientVehicles(
  clientId: string | undefined,
  params?: { page?: number; pageSize?: number; q?: string; participation?: string },
) {
  const { page = 1, pageSize = 50, q = '', participation = 'all' } = params ?? {}
  return useQuery({
    queryKey: ['clients', clientId, 'vehicles', page, pageSize, q, participation],
    queryFn: async () => {
      const { data } = await api.get<ClientVehicleList>(`/clients/${clientId}/vehicles`, {
        params: {
          page,
          page_size: pageSize,
          q: q || undefined,
          participation: participation || undefined,
        },
      })
      return data
    },
    enabled: !!clientId,
    placeholderData: (prev) => prev, // 페이지 전환 시 이전 결과 유지(깜빡임 방지)
  })
}

/** fleet 양식(xlsx) 다운로드 — Content-Disposition filename* 파싱은 downloadExport에 위임 */
export function useFleetTemplate() {
  return useMutation({
    mutationFn: async () => {
      await downloadExport('/fleet/template', {}, '전국버스명부_양식.xlsx')
    },
  })
}

/** fleet 미리보기 — 반영 전 행별 검증(DB 무변경). 반영 시 같은 파일을 useImportFleet로 재전송 */
export function useFleetPreview() {
  return useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      const { data } = await api.post<FleetPreviewResult>('/fleet/preview', fd)
      return data
    },
  })
}

/** 전국 버스 명부(fleet) 엑셀 일괄 업로드 — 전역 마스터라 clients 전체를 넓게 무효화 */
export function useImportFleet(clientId?: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      const { data } = await api.post<FleetImportResult>('/fleet/import', fd)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
      if (clientId) queryClient.invalidateQueries({ queryKey: ['clients', clientId] })
    },
  })
}

// ── 운수사 계약대수 현황(F2/F3) ──────────────────────────────────────────
/** 계약대수 현황 미리보기 — 원본 엑셀+월(YYYY-MM), DB 무변경. 반영 시 같은 파일 재전송 */
export function useFleetStatusPreview() {
  return useMutation({
    mutationFn: async ({ file, period }: { file: File; period: string }) => {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('period', period)
      const { data } = await api.post<FleetStatusPreviewResult>('/fleet-status/preview', fd)
      return data
    },
  })
}

/** 계약대수 현황 반영 — (고객사×월) upsert. clients·현황 쿼리 무효화 */
export function useFleetStatusCommit() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ file, period }: { file: File; period: string }) => {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('period', period)
      const { data } = await api.post<FleetStatusCommitResult>('/fleet-status/commit', fd)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
      queryClient.invalidateQueries({ queryKey: ['fleet-status'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

/** 미매칭 운수사(계약대수엔 있으나 마스터에 없음) → 운수사 표준 양식 xlsx 다운로드 */
export function useExportUnmatchedTransport() {
  return useMutation({
    mutationFn: async (period?: string) => {
      await downloadExport(
        '/fleet-status/unmatched-export',
        period ? { period } : {},
        '미매칭_운수사_표준양식.xlsx',
      )
    },
  })
}

/** 고객사 현황 탭 — 월별 대수 추이 + 수작업 관리 */
export function useFleetClientStatus(clientId: string | undefined) {
  return useQuery({
    queryKey: ['fleet-status', clientId],
    queryFn: async () => {
      const { data } = await api.get<FleetClientStatus>(`/fleet-status/client/${clientId}`)
      return data
    },
    enabled: !!clientId,
  })
}

/** 수작업 관리 저장(업로드와 독립) */
export function useSaveFleetMgmt(clientId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: FleetMgmt) => {
      const { data } = await api.put<FleetMgmt>(
        `/fleet-status/client/${clientId}/mgmt`,
        payload,
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fleet-status', clientId] })
    },
  })
}

export function useSaveClientVehicle(clientId: string | undefined, vehicleId?: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: ClientVehiclePayload) => {
      const { data } = vehicleId
        ? await api.put<ClientVehicle>(`/clients/${clientId}/vehicles/${vehicleId}`, payload)
        : await api.post<ClientVehicle>(`/clients/${clientId}/vehicles`, payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients', clientId, 'vehicles'] })
    },
  })
}

export function useDeleteClientVehicle(clientId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (vehicleId: string) => {
      await api.delete(`/clients/${clientId}/vehicles/${vehicleId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients', clientId, 'vehicles'] })
    },
  })
}
