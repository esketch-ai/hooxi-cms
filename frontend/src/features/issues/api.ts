// SCR-02 이슈 보드 API 훅 — 이슈 = tb_activity_history(activity_type=ISSUE)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import { unwrapList } from '../../lib/api/queries'
import type { ActivityHistory, IssueComment, IssueStatus, Paginated } from '../../types'

export function useIssues() {
  return useQuery({
    queryKey: ['issues'],
    queryFn: async () => {
      const { data } = await api.get<ActivityHistory[] | Paginated<ActivityHistory>>(
        '/histories',
        { params: { activity_type: 'ISSUE', page_size: 200 } },
      )
      return unwrapList(data).items
    },
  })
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
