// SCR-14 시스템 설정·감사 로그 API 훅 — backend/routers/config.py·audit.py 실계약 기준
// GET /config → List[ConfigOut{config_key,config_value,description,updated_by_name,updated_at,is_default}]
// PUT /config/{key} {config_value: string(JSON)} — 422: JSON·구조 검증 실패
// GET /config/{key}/history → {items:[ConfigHistoryOut], total}
// GET /audit-logs?action=&date_from=&date_to=&page=&page_size= → {items:[AuditLogOut], total}
// (초기 계약안 key/value 필드명도 정규화해 수용)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import { unwrapList } from '../../lib/api/queries'
import type { Paginated } from '../../types'

// ── 타입 ─────────────────────────────────────────────────────────────
export interface ConfigItem {
  key: string
  value: string
  description?: string | null
  updated_at?: string | null
  updated_by?: string | null
  updated_by_name?: string | null
  /** 미저장 기본값 (tb_config에 행 없음 — 서버 기본값 노출) */
  is_default?: boolean
}

export interface ConfigHistoryItem {
  history_id?: string
  config_key?: string
  old_value?: string | null
  new_value?: string | null
  updated_by?: string | null
  updated_by_name?: string | null
  created_at?: string | null
}

export interface AuditLogItem {
  log_id: string
  actor_id?: string | null
  actor_name?: string | null
  action: string
  target_type?: string | null
  target_id?: string | null
  old_value?: string | null
  new_value?: string | null
  created_at?: string | null
}

export interface AuditLogFilters {
  action?: string
  date_from?: string
  date_to?: string
  page: number
  page_size: number
}

// ── 정규화 (key/config_key · value/config_value 양쪽 수용) ────────────
interface RawConfigItem extends Partial<ConfigItem> {
  config_key?: string
  config_value?: string | null
}

function normalizeConfig(raw: RawConfigItem): ConfigItem {
  return {
    key: raw.key ?? raw.config_key ?? '',
    value: raw.value ?? raw.config_value ?? '',
    description: raw.description ?? null,
    updated_at: raw.updated_at ?? null,
    updated_by: raw.updated_by ?? null,
    updated_by_name: raw.updated_by_name ?? null,
    is_default: raw.is_default ?? false,
  }
}

// ── 시스템 설정 ──────────────────────────────────────────────────────
export function useConfigList(enabled = true) {
  return useQuery({
    queryKey: ['config'],
    queryFn: async () => {
      const { data } = await api.get<RawConfigItem[] | Paginated<RawConfigItem>>('/config')
      return unwrapList(data)
        .items.map(normalizeConfig)
        .filter((item) => item.key)
    },
    enabled,
  })
}

export function useSaveConfig() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ key, value }: { key: string; value: string }) => {
      // 실계약(schemas.ConfigUpdate)은 config_value — 구계약(value)도 병기 전송(무해)
      const { data } = await api.put(`/config/${encodeURIComponent(key)}`, {
        config_value: value,
        value,
      })
      return data
    },
    onSuccess: (_data, { key }) => {
      queryClient.invalidateQueries({ queryKey: ['config'] })
      queryClient.invalidateQueries({ queryKey: ['config-history', key] })
      // 설정이 메일 템플릿·상담 키워드 등에 영향 — 관련 캐시 무효화
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useConfigHistory(key: string, enabled: boolean) {
  return useQuery({
    queryKey: ['config-history', key],
    queryFn: async () => {
      const { data } = await api.get<ConfigHistoryItem[] | Paginated<ConfigHistoryItem>>(
        `/config/${encodeURIComponent(key)}/history`,
      )
      return unwrapList(data).items
    },
    enabled,
  })
}

// ── 연동 관리 (외부 연동 자격증명) ───────────────────────────────────
// 계약안 (backend/routers/integrations.py 배포 전 가정):
// GET  /integrations → [{name, label, fields:[{key,label,secret,required,configured,source}]}]
// PUT  /integrations/{name} {values:{KEY: value|null}} — 전달 키만 갱신, null은 삭제
// POST /integrations/{name}/test → {ok, message}
// POST /integrations/dropbox/oauth/authorize-url → {url}
// POST /integrations/dropbox/oauth/exchange {code} → {ok, message}
// GET  /integrations/kakao_bot/webhook-url → {url}

export interface IntegrationField {
  key: string
  label: string
  secret?: boolean
  required?: boolean
  configured?: boolean
  source?: 'db' | 'env' | null
}

export interface Integration {
  name: string
  label: string
  description?: string | null
  fields: IntegrationField[]
}

export interface IntegrationTestResult {
  ok: boolean
  message?: string | null
}

export function useIntegrations(enabled = true) {
  return useQuery({
    queryKey: ['integrations'],
    queryFn: async () => {
      const { data } = await api.get<Integration[] | Paginated<Integration>>('/integrations')
      return unwrapList(data).items.filter((i) => i.name)
    },
    enabled,
    retry: false,
  })
}

export function useSaveIntegration() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      name,
      values,
    }: {
      name: string
      values: Record<string, string | null>
    }) => {
      const { data } = await api.put(`/integrations/${encodeURIComponent(name)}`, { values })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations'] })
    },
  })
}

export function useTestIntegration() {
  return useMutation({
    mutationFn: async (name: string) => {
      const { data } = await api.post<IntegrationTestResult>(
        `/integrations/${encodeURIComponent(name)}/test`,
      )
      return data
    },
  })
}

export function useDropboxAuthorizeUrl() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ url: string }>('/integrations/dropbox/oauth/authorize-url')
      return data
    },
  })
}

export function useDropboxExchange() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (code: string) => {
      const { data } = await api.post<IntegrationTestResult>(
        '/integrations/dropbox/oauth/exchange',
        { code },
      )
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations'] })
    },
  })
}

/** 오픈빌더 폴백 블록에 등록할 웹훅 URL — 엔드포인트 미배포(404) 시 비노출 */
export function useKakaoWebhookUrl(enabled: boolean) {
  return useQuery({
    queryKey: ['integrations', 'kakao-webhook-url'],
    queryFn: async () => {
      const { data } = await api.get<{ url: string }>('/integrations/kakao_bot/webhook-url')
      return data
    },
    enabled,
    retry: false,
    staleTime: 60_000,
  })
}

// ── 감사 로그 ────────────────────────────────────────────────────────
export function useAuditLogs(filters: AuditLogFilters, enabled = true) {
  return useQuery({
    queryKey: ['audit-logs', filters],
    queryFn: async () => {
      const params: Record<string, string | number> = {
        page: filters.page,
        page_size: filters.page_size,
      }
      if (filters.action) params.action = filters.action
      if (filters.date_from) params.date_from = filters.date_from
      if (filters.date_to) params.date_to = filters.date_to
      const { data } = await api.get<AuditLogItem[] | Paginated<AuditLogItem>>('/audit-logs', {
        params,
      })
      return unwrapList(data)
    },
    enabled,
    placeholderData: (prev) => prev,
  })
}
