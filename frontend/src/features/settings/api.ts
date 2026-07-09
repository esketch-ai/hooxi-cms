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
      // 설정이 대시보드 퍼널·상담 키워드에 영향 — 관련 캐시 무효화
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
