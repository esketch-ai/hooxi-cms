// 공용 서버 상태 훅 — 여러 화면에서 재사용하는 셀렉트 옵션(고객사·사용자) 등
import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type {
  ChatBadge,
  Client,
  Code,
  Document,
  DropboxTreeResponse,
  Paginated,
  User,
} from '../../types'

/**
 * Dropbox 폴더 라이브 조회 — endpoint별 재사용(고객사 폴더·공용 발송자료 폴더 공통).
 * endpoint 예: `/clients/{id}/dropbox/tree`, `/segments/dropbox/tree`. null이면 비활성.
 */
export function useDropboxTree(endpoint: string | null, path: string | null) {
  return useQuery({
    queryKey: ['dropbox-tree', endpoint, path],
    enabled: !!endpoint,
    retry: false, // 409/503/403은 재시도 무의미 — 즉시 안내
    queryFn: async () => {
      const { data } = await api.get<DropboxTreeResponse>(endpoint as string, {
        params: path ? { path } : undefined,
      })
      return data
    },
  })
}

/**
 * 공통 코드 마스터 조회 (tb_code). 드롭다운 옵션 + 코드값→표시명 매핑을 함께 제공.
 * - options: 활성 코드만 (신규 선택지용)
 * - labelOf(code): 표시명 반환, 없으면 코드값 원문(구분 삭제/변동 시에도 오표시 방지)
 * include_inactive=true로 전체를 받아 비활성 코드도 라벨 해석은 되게 한다.
 */
export function useCodes(category: string) {
  const query = useQuery({
    queryKey: ['codes', category],
    queryFn: async () => {
      const { data } = await api.get<Code[]>('/codes', {
        params: { category, include_inactive: true },
      })
      return data
    },
    staleTime: 5 * 60_000,
  })

  const codes = query.data ?? []
  const labelMap = useMemo(() => {
    const m: Record<string, string> = {}
    for (const c of codes) m[c.code] = c.label
    return m
  }, [codes])

  const options = useMemo(
    () =>
      codes
        .filter((c) => c.active === 'Y')
        .map((c) => ({ value: c.code, label: c.label })),
    [codes],
  )

  const labelOf = (code?: string | null) => (code ? labelMap[code] ?? code : '')

  return { ...query, codes, options, labelOf }
}

/** 배열/Paginated 어느 쪽이 와도 items·total로 정규화 */
export function unwrapList<T>(data: T[] | Paginated<T> | null | undefined): {
  items: T[]
  total: number
} {
  if (!data) return { items: [], total: 0 }
  if (Array.isArray(data)) return { items: data, total: data.length }
  return { items: data.items ?? [], total: data.total ?? data.items?.length ?? 0 }
}

/** 고객사 셀렉트 옵션용 전체 목록 (폼·필터 공용) */
export function useClientOptions(opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['clients', 'options'],
    queryFn: async () => {
      // 경량 전건 옵션 API — 고객사 200곳 초과 시 뒷번호가 누락돼 UUID가 노출되던 문제의
      // 근본 해결(집계 없는 최소 필드, 페이지네이션 없음). enforce 모드에서도 전역 허용.
      const { data } = await api.get<Client[]>('/clients/options')
      return data
    },
    staleTime: 60_000,
    enabled: opts?.enabled ?? true, // OBSERVER 등 /clients 차단 역할은 enabled:false로 호출 자체 억제
  })
}

/** 활동 이력 첨부 문서 목록 — GET /documents?history_id= (SCR-05 확장 행 등) */
export function useHistoryDocuments(historyId: string | null | undefined) {
  return useQuery({
    queryKey: ['documents', 'history', historyId],
    queryFn: async () => {
      const { data } = await api.get<Document[] | Paginated<Document>>('/documents', {
        params: { history_id: historyId, page_size: 100 },
      })
      return unwrapList(data).items
    },
    enabled: !!historyId,
  })
}

/** 카카오 상담 LNB 뱃지 — GET /chat/badge 15초 폴링 (Sidebar·BottomNav 공용) */
export function useChatBadge() {
  return useQuery({
    queryKey: ['chat', 'badge'],
    queryFn: async () => {
      try {
        const { data } = await api.get<ChatBadge>('/chat/badge')
        return { waiting: data?.waiting ?? 0 }
      } catch {
        // 백엔드 미배포·미설정 시 뱃지 숨김 (콘솔 에러 폴링 방지)
        return { waiting: 0 }
      }
    },
    refetchInterval: 15_000,
    staleTime: 10_000,
  })
}

/** 사용자(담당 PM·작성자) 셀렉트 옵션 — MANAGER 미만 403이면 빈 목록 폴백 */
export function useUserOptions() {
  return useQuery({
    queryKey: ['users', 'options'],
    queryFn: async () => {
      try {
        const { data } = await api.get<User[]>('/users', { params: { status: 'ACTIVE' } })
        return data
      } catch {
        return [] as User[]
      }
    },
    staleTime: 300_000,
  })
}

/** 자산별 사진 목록 — GET /documents?asset_id= (SCR-04 사진 보기 모달 등) */
export function useAssetDocuments(assetId: string | null | undefined) {
  return useQuery({
    queryKey: ['documents', 'asset', assetId],
    queryFn: async () => {
      const { data } = await api.get<Document[] | Paginated<Document>>('/documents', {
        params: { asset_id: assetId, page_size: 100 },
      })
      return unwrapList(data).items
    },
    enabled: !!assetId,
  })
}

/** 삭제 불가(보존) 문서 유형 — 백엔드 documents.py _DELETABLE_DOC_TYPES와 정합.
 *  리포트 발송 파일·고객 확인 서명은 보존 대상이라 삭제 버튼을 노출하지 않는다. */
const PRESERVED_DOC_TYPES = ['REPORT', 'SIGN']
export function isDeletableDoc(docType: string | null | undefined): boolean {
  return !!docType && !PRESERVED_DOC_TYPES.includes(docType)
}

/** 문서 삭제 — 사진·일반문서만(백엔드가 REPORT/SIGN은 403). 모든 문서 목록 무효화. */
export function useDeleteDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (docId: string) => {
      await api.delete(`/documents/${docId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })
}

// ── Dropbox 폴더명 규칙 점검/교정(reconcile) — ADMIN 전용 ─────────────
// 미리보기(dry-run)로 이동/충돌/유지 후보를 계산 후, 적용으로 규칙 경로로 이동.
export interface ReconcilePreviewItem {
  client_id: string
  company_name: string
  current_path: string
  proposed_path: string
  action: 'skip_match' | 'move' | 'conflict'
  reason: 'root_changed' | 'name_changed' | null
}

export interface ReconcilePreview {
  total: number
  move_count: number
  conflict_count: number
  skip_count: number
  items: ReconcilePreviewItem[]
}

export interface ReconcileApplyDetail {
  client_id: string
  from_path: string
  to_path: string
  result: 'moved' | 'conflict' | 'failed'
}

export interface ReconcileApply {
  total_candidates: number
  moved: number
  conflicts: number
  failed: number
  details: ReconcileApplyDetail[]
}

// 미리보기(dry-run) — 본문 없음. 미설정 503/권한 403은 error.response.data.detail로 안내.
export function usePreviewReconcile() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<ReconcilePreview>(
        '/batch/reconcile-dropbox-folders/preview',
      )
      return data
    },
  })
}

// 적용 — 규칙 경로로 실제 이동. 파일은 보존(폴더 이동만).
export function useApplyReconcile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<ReconcileApply>('/batch/reconcile-dropbox-folders/apply')
      return data
    },
    onSuccess: () => {
      // 폴더 경로 변동 반영
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['clients'] })
      queryClient.invalidateQueries({ queryKey: ['dropbox-tree'] })
    },
  })
}


/** 로그인 화면 공개 설정(무인증) — 카카오 채널 URL 등. 실패 시 null(버튼 숨김) */
export function useLoginConfig() {
  return useQuery({
    queryKey: ['auth', 'login-config'],
    queryFn: async () => {
      try {
        const { data } = await api.get<{ kakao_channel_url?: string | null }>('/auth/login-config')
        return data
      } catch {
        return { kakao_channel_url: null }
      }
    },
    staleTime: 10 * 60_000,
    retry: false,
  })
}
