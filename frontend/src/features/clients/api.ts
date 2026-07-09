// SCR-03·03D API 훅 — 플랜 §5 엔드포인트 기준
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import { unwrapList } from '../../lib/api/queries'
import type {
  ActivityHistory,
  Asset,
  Client,
  ClientPayload,
  Document,
  Paginated,
  ReportDelivery,
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
