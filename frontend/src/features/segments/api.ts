// 세그먼트 보고서 발송 API 훅 — backend/routers/segments.py 계약 준수
// (preview는 POST지만 조회 성격 — useQuery + queryKey에 criteria 포함)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import type {
  Segment,
  SegmentCriteria,
  SegmentFacets,
  SegmentPayload,
  SegmentPreviewResponse,
  SegmentSend,
  SegmentSendDetailOut,
  SegmentSendPayload,
  SegmentSendResponse,
} from '../../types'

/** 저장된 세그먼트 목록 — 활성만 (soft 삭제 제외) */
export function useSegments() {
  return useQuery({
    queryKey: ['segments', 'list'],
    queryFn: async () => {
      const { data } = await api.get<Segment[]>('/segments')
      return data
    },
  })
}

/** 조건 축 선택지 — region만 서버 제공(나머지 축은 useCodes·useProjectOptions 재사용) */
export function useSegmentFacets() {
  return useQuery({
    queryKey: ['segments', 'facets'],
    queryFn: async () => {
      const { data } = await api.get<SegmentFacets>('/segments/facets')
      return data
    },
    staleTime: 5 * 60_000,
  })
}

/** 실시간 미리보기 — 대상 고객사 + 수신 가능 여부 (호출부에서 criteria 디바운스) */
export function useSegmentPreview(criteria: SegmentCriteria) {
  return useQuery({
    queryKey: ['segments', 'preview', criteria],
    queryFn: async () => {
      const { data } = await api.post<SegmentPreviewResponse>('/segments/preview', {
        criteria,
      })
      return data
    },
    // 조건 변경 직후 이전 결과 유지 — 카운트 깜빡임 방지
    placeholderData: (prev) => prev,
  })
}

function useInvalidateSegments() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ['segments'] })
}

/** 세그먼트 저장 — segmentId 있으면 수정(PUT), 없으면 생성(POST) */
export function useSaveSegment() {
  const invalidate = useInvalidateSegments()
  return useMutation({
    mutationFn: async ({
      segmentId,
      payload,
    }: {
      segmentId?: string
      payload: SegmentPayload
    }) => {
      const { data } = segmentId
        ? await api.put<Segment>(`/segments/${segmentId}`, payload)
        : await api.post<Segment>('/segments', payload)
      return data
    },
    onSuccess: () => invalidate(),
  })
}

/** 세그먼트 삭제 — soft(active=N), 발송 이력 참조 보존 */
export function useDeleteSegment() {
  const invalidate = useInvalidateSegments()
  return useMutation({
    mutationFn: async (segmentId: string) => {
      await api.delete(`/segments/${segmentId}`)
    },
    onSuccess: () => invalidate(),
  })
}

/** 발송 실행 — segmentId 있으면 저장 세그먼트 발송, 없으면 즉석(criteria 필수).
 *  건별 메일 발송으로 오래 걸릴 수 있어 timeout 상향 (배치 관용구) */
export function useSendSegment() {
  const invalidate = useInvalidateSegments()
  return useMutation({
    mutationFn: async ({
      segmentId,
      payload,
    }: {
      segmentId?: string
      payload: SegmentSendPayload
    }) => {
      const url = segmentId ? `/segments/${segmentId}/send` : '/segments/send'
      const { data } = await api.post<SegmentSendResponse>(url, payload, {
        timeout: 120_000,
      })
      return data
    },
    onSuccess: () => invalidate(),
  })
}

/** 발송 실행 이력 목록 — 최신순 */
export function useSegmentSends() {
  return useQuery({
    queryKey: ['segments', 'sends'],
    queryFn: async () => {
      const { data } = await api.get<SegmentSend[]>('/segments/sends')
      return data
    },
  })
}

/** 발송 이력 상세 — 고객사별 SUCCESS/FAIL 로그 포함 */
export function useSegmentSendDetail(sendId: string | null | undefined) {
  return useQuery({
    queryKey: ['segments', 'sends', sendId],
    queryFn: async () => {
      const { data } = await api.get<SegmentSendDetailOut>(`/segments/sends/${sendId}`)
      return data
    },
    enabled: !!sendId,
  })
}
