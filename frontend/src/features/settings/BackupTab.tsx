// SCR-14 백업·복구 탭 (ADMIN 전용) — Cloud SQL 자동 백업(매일 05:00 KST, 15일 보관)
// 일자별 선택 복구: 2단 확인('복구' 타이핑) + 진행 상태 폴링 + 감사 로그(서버 기록)
import { useEffect, useRef, useState } from 'react'
import { ArrowCounterClockwise, CircleNotch, DownloadSimple, Warning } from '@phosphor-icons/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { EmptyState } from '../../components/EmptyState'
import { Modal } from '../../components/Modal'
import { Skeleton } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { api } from '../../lib/api/client'
import { parseServerUtc } from '../../lib/format'

interface BackupRun {
  backup_run_id: string
  backup_type: string | null // AUTOMATED / ON_DEMAND
  status: string | null // SUCCESSFUL / FAILED / RUNNING
  start_time: string | null
  end_time: string | null
  description: string | null
}

interface BackupList {
  policy: { schedule: string; retention_days: number }
  items: BackupRun[]
}

interface BackupOperation {
  operation_id: string
  status: string // PENDING / RUNNING / DONE
  error?: string | null
}

/** UTC ISO → KST 표기 — tz 정보 없는 서버 시각도 UTC로 간주 */
function fmtKst(iso: string | null): string {
  if (!iso) return '—'
  const d = parseServerUtc(iso)
  return d.toLocaleString('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const TYPE_LABELS: Record<string, string> = {
  AUTOMATED: '자동',
  ON_DEMAND: '수동',
}

const STATUS_SPECS: Record<string, { label: string; cls: string }> = {
  SUCCESSFUL: { label: '성공', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  FAILED: { label: '실패', cls: 'bg-rose-50 text-rose-700 border-rose-200' },
  RUNNING: { label: '진행중', cls: 'bg-blue-50 text-blue-700 border-blue-200' },
  ENQUEUED: { label: '대기', cls: 'bg-slate-100 text-slate-600 border-slate-200' },
}

export function BackupTab() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()

  const [restoreTarget, setRestoreTarget] = useState<BackupRun | null>(null)
  const [confirmWord, setConfirmWord] = useState('')
  // 진행 중 작업 폴링 (백업 또는 복구)
  const [pendingOp, setPendingOp] = useState<{ id: string; kind: '백업' | '복구' } | null>(null)
  const pollRef = useRef<number | null>(null)

  const { data, isLoading, error } = useQuery<BackupList>({
    queryKey: ['backups'],
    queryFn: async () => (await api.get('/backups')).data,
    retry: false,
  })

  const createBackup = useMutation({
    mutationFn: async () => (await api.post<BackupOperation>('/backups')).data,
    onSuccess: (op) => {
      showToast('백업을 시작했습니다. 완료까지 수 분 걸릴 수 있습니다.', 'success')
      setPendingOp({ id: op.operation_id, kind: '백업' })
    },
    onError: () => showToast('백업 시작에 실패했습니다.', 'danger'),
  })

  const restore = useMutation({
    mutationFn: async (run: BackupRun) =>
      (
        await api.post<BackupOperation>(`/backups/${run.backup_run_id}/restore`, {
          confirm: confirmWord,
          backup_date: fmtKst(run.start_time),
        })
      ).data,
    onSuccess: (op) => {
      setRestoreTarget(null)
      setConfirmWord('')
      showToast('복구를 시작했습니다. 복구 중 서비스가 일시 중단됩니다.', 'success')
      setPendingOp({ id: op.operation_id, kind: '복구' })
    },
    onError: () => showToast('복구 시작에 실패했습니다.', 'danger'),
  })

  // 작업 진행 폴링 — DONE이면 목록 갱신
  useEffect(() => {
    if (!pendingOp) return
    const tick = async () => {
      try {
        const { data: op } = await api.get<BackupOperation>(
          `/backups/operations/${encodeURIComponent(pendingOp.id)}`,
        )
        if (op.status === 'DONE') {
          setPendingOp(null)
          if (op.error) {
            showToast(`${pendingOp.kind} 작업이 실패했습니다: ${op.error}`, 'danger')
          } else {
            showToast(`${pendingOp.kind}가 완료되었습니다.`, 'success')
          }
          queryClient.invalidateQueries({ queryKey: ['backups'] })
        }
      } catch {
        // 복구 중에는 서비스 자체가 잠시 응답하지 않을 수 있음 — 폴링 유지
      }
    }
    pollRef.current = window.setInterval(tick, 5000)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [pendingOp, queryClient, showToast])

  if (isLoading)
    return (
      <div className="space-y-2">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    )

  // 미설정(로컬 등) — 503
  if (error) {
    return (
      <EmptyState
        title="백업 연동이 설정되지 않았습니다"
        description="Cloud Run 환경에서 GCP_PROJECT / CLOUDSQL_INSTANCE 환경변수 설정 시 활성화됩니다."
      />
    )
  }

  const items = data?.items ?? []

  return (
    <div className="space-y-4">
      {/* 정책 + 수동 백업 */}
      <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-sm font-semibold text-slate-800">자동 백업 정책</div>
          <div className="mt-1 text-sm text-slate-500">
            {data?.policy.schedule} 데이터베이스 백업 · 최근 {data?.policy.retention_days}일치
            보관 · 아래 목록에서 일자를 선택해 복구할 수 있습니다
          </div>
        </div>
        <button
          type="button"
          onClick={() => createBackup.mutate()}
          disabled={createBackup.isPending || !!pendingOp}
          className="flex h-10 shrink-0 items-center justify-center gap-1.5 rounded-lg bg-slate-800 px-4 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-60"
        >
          {createBackup.isPending || pendingOp?.kind === '백업' ? (
            <CircleNotch size={15} className="animate-spin" />
          ) : (
            <DownloadSimple size={15} />
          )}
          지금 백업
        </button>
      </div>

      {pendingOp && (
        <div className="flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2.5 text-sm text-blue-700">
          <CircleNotch size={15} className="animate-spin" />
          {pendingOp.kind} 작업이 진행 중입니다{pendingOp.kind === '복구' && ' — 완료까지 서비스가 일시 중단될 수 있습니다'}
        </div>
      )}

      {/* 백업 목록 */}
      {items.length === 0 ? (
        <EmptyState
          title="백업 이력이 없습니다"
          description="첫 자동 백업은 다음 05:00(KST)에 생성됩니다. [지금 백업]으로 즉시 생성할 수도 있습니다."
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                <th className="px-4 py-3 font-medium">백업 시각 (KST)</th>
                <th className="px-4 py-3 font-medium">유형</th>
                <th className="px-4 py-3 font-medium">상태</th>
                <th className="px-4 py-3 font-medium">비고</th>
                <th className="px-4 py-3 text-right font-medium">복구</th>
              </tr>
            </thead>
            <tbody>
              {items.map((run) => {
                const status = STATUS_SPECS[run.status ?? ''] ?? {
                  label: run.status ?? '—',
                  cls: 'bg-slate-100 text-slate-600 border-slate-200',
                }
                return (
                  <tr key={run.backup_run_id} className="border-b border-slate-50 last:border-0">
                    <td className="px-4 py-3 font-medium text-slate-800">
                      {fmtKst(run.start_time)}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {TYPE_LABELS[run.backup_type ?? ''] ?? run.backup_type ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${status.cls}`}
                      >
                        {status.label}
                      </span>
                    </td>
                    <td className="max-w-[200px] truncate px-4 py-3 text-xs text-slate-400">
                      {run.description ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => {
                          setConfirmWord('')
                          setRestoreTarget(run)
                        }}
                        disabled={run.status !== 'SUCCESSFUL' || !!pendingOp}
                        className="inline-flex items-center gap-1 rounded-lg border border-rose-200 px-3 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-40"
                      >
                        <ArrowCounterClockwise size={13} />이 시점으로 복구
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* 복구 확인 Modal — 2단 확인('복구' 타이핑) */}
      <Modal
        open={!!restoreTarget}
        onClose={() => setRestoreTarget(null)}
        title="데이터베이스 복구"
      >
        {restoreTarget && (
          <div className="space-y-4">
            <div className="flex gap-2.5 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm leading-relaxed text-rose-700">
              <Warning size={20} className="mt-0.5 shrink-0" />
              <div>
                <b>{fmtKst(restoreTarget.start_time)}</b> 백업 시점으로 데이터베이스 전체가
                되돌아갑니다.
                <br />• 이 시점 <b>이후에 입력된 모든 데이터가 사라집니다</b>
                <br />• 복구 중 수 분간 <b>서비스가 중단</b>됩니다
                <br />• 이 작업은 감사 로그에 기록됩니다
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                계속하려면 <b className="text-rose-600">복구</b>를 입력하세요
              </label>
              <input
                value={confirmWord}
                onChange={(e) => setConfirmWord(e.target.value)}
                className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm focus:border-rose-400 focus:outline-none"
                placeholder="복구"
              />
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setRestoreTarget(null)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
              >
                취소
              </button>
              <button
                type="button"
                disabled={confirmWord.trim() !== '복구' || restore.isPending}
                onClick={() => restore.mutate(restoreTarget)}
                className="flex items-center gap-1.5 rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-500 disabled:opacity-50"
              >
                {restore.isPending && <CircleNotch size={14} className="animate-spin" />}
                복구 실행
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
