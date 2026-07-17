// SCR-02 이슈 보드 API 훅 — 이슈 = tb_activity_history(activity_type=ISSUE)
import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import { unwrapList } from '../../lib/api/queries'
import { fmtDate } from '../../lib/format'
import type { ActivityHistory, IssueComment, IssueStatus, Paginated } from '../../types'

/**
 * 보드 데이터 2쿼리 병합 — 200건 절단으로 오래된 OPEN/HOLD가 실종되던 문제 해소.
 * - 미종결(OPEN,IN_PROGRESS,HOLD): 200건 초과분은 activeTotal로 노출해 화면에서 경고(침묵 절단 금지)
 * - 완료(CLOSED): 최근 7일 갱신분만 조회해 예산을 아낌
 */
export function useIssues() {
  const active = useQuery({
    queryKey: ['issues', 'active'],
    queryFn: async () => {
      const { data } = await api.get<ActivityHistory[] | Paginated<ActivityHistory>>(
        '/histories',
        {
          params: {
            activity_type: 'ISSUE',
            issue_status: 'OPEN,IN_PROGRESS,HOLD',
            page_size: 200,
          },
        },
      )
      return unwrapList(data)
    },
  })
  const closed = useQuery({
    queryKey: ['issues', 'closed'],
    queryFn: async () => {
      const { data } = await api.get<ActivityHistory[] | Paginated<ActivityHistory>>(
        '/histories',
        {
          params: {
            activity_type: 'ISSUE',
            issue_status: 'CLOSED',
            closed_since: fmtDate(new Date(Date.now() - 7 * 86_400_000)),
            page_size: 200,
          },
        },
      )
      return unwrapList(data)
    },
  })

  // 두 쿼리 사이에 상태가 바뀐 이슈가 양쪽 응답에 실릴 수 있어 history_id로 dedupe(뒤=최신 우선)
  const data = useMemo(() => {
    const byId = new Map<string, ActivityHistory>()
    for (const item of [...(active.data?.items ?? []), ...(closed.data?.items ?? [])]) {
      byId.set(item.history_id, item)
    }
    return [...byId.values()]
  }, [active.data, closed.data])
  return {
    data,
    isLoading: active.isLoading || closed.isLoading,
    isError: active.isError || closed.isError,
    refetch: () => Promise.all([active.refetch(), closed.refetch()]),
    /** 미종결 전체 건수 — items보다 크면 200건 절단 발생(운영 경고 대상) */
    activeTotal: active.data?.total ?? 0,
    activeShown: active.data?.items.length ?? 0,
  }
}

/** 칸반 드래그·Drawer에서 상태 변경 — PUT /histories/{id}/status */
export function useChangeIssueStatus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      historyId,
      issueStatus,
    }: {
      historyId: string
      issueStatus: IssueStatus
    }) => {
      const { data } = await api.put(`/histories/${historyId}/status`, {
        issue_status: issueStatus,
      })
      return data
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['issues'] })
      queryClient.invalidateQueries({ queryKey: ['histories'] })
      queryClient.invalidateQueries({ queryKey: ['issues', variables.historyId, 'comments'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

/** 코멘트 스레드 (tb_issue_comment) — 상태 변경 이력 포함 */
export function useIssueComments(historyId: string | undefined) {
  return useQuery({
    queryKey: ['issues', historyId, 'comments'],
    queryFn: async () => {
      const { data } = await api.get<IssueComment[] | Paginated<IssueComment>>(
        `/histories/${historyId}/comments`,
      )
      return unwrapList(data).items
    },
    enabled: !!historyId,
  })
}

export function useAddIssueComment(historyId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (content: string) => {
      const { data } = await api.post(`/histories/${historyId}/comments`, { content })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issues', historyId, 'comments'] })
    },
  })
}
