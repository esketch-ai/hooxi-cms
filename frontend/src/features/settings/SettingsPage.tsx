// SCR-14 환경 설정 — 계정 관리(P1) + 시스템 설정·감사 로그(P3, ADMIN 전용)
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  LockKeyOpen,
  Prohibit,
  ShieldCheck,
  UserCircle,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { DataTable, type Column } from '../../components/DataTable'
import { EmptyState } from '../../components/EmptyState'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { Modal } from '../../components/Modal'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import { api } from '../../lib/api/client'
import { fmtDate } from '../../lib/format'
import type { User, UserRole } from '../../types'
import { SystemConfigTab } from './SystemConfigTab'
import { AuditLogTab } from './AuditLogTab'
import { BackupTab } from './BackupTab'

type TabKey = 'accounts' | 'system' | 'backup' | 'audit'

const ROLE_LABELS: Record<UserRole, string> = {
  ADMIN: '관리자',
  MANAGER: '팀장',
  STAFF: '실무',
}

const STATUS_BADGES: Record<string, { label: string; cls: string }> = {
  PENDING: { label: '승인 대기', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  ACTIVE: { label: '활성', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  INACTIVE: { label: '비활성', cls: 'bg-slate-100 text-slate-500 border-slate-200' },
}

export function SettingsPage() {
  const { user: me } = useAuth()
  const [tab, setTab] = useState<TabKey>('accounts')
  const isAdmin = me?.role === 'ADMIN'
  const canView = isAdmin || me?.role === 'MANAGER'

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader title="환경 설정" subtitle="계정·권한·시스템 설정·감사 로그 (SCR-14)" />

      {/* 탭 */}
      <div className="flex gap-1 border-b border-slate-200">
        {(
          [
            { key: 'accounts', label: '계정 관리' },
            { key: 'system', label: '시스템 설정' },
            { key: 'backup', label: '백업·복구' },
            { key: 'audit', label: '감사 로그' },
          ] as { key: TabKey; label: string }[]
        ).map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`border-b-2 px-3.5 py-2.5 text-sm font-medium transition-colors ${
              tab === t.key
                ? 'border-slate-800 text-slate-900'
                : 'border-transparent text-slate-400 hover:text-slate-600'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'accounts' &&
        (canView ? (
          <AccountsTab isAdmin={isAdmin} meId={me?.user_id ?? ''} />
        ) : (
          <EmptyState
            icon={<ShieldCheck size={36} />}
            title="접근 권한이 없습니다"
            description="계정 관리는 관리자(ADMIN)·팀장(MANAGER)만 조회할 수 있습니다."
          />
        ))}
      {tab === 'system' &&
        (isAdmin ? <SystemConfigTab /> : <AdminOnlyNotice feature="시스템 설정" />)}
      {tab === 'backup' &&
        (isAdmin ? <BackupTab /> : <AdminOnlyNotice feature="백업·복구" />)}
      {tab === 'audit' &&
        (isAdmin ? <AuditLogTab /> : <AdminOnlyNotice feature="감사 로그" />)}
    </div>
  )
}

// ── ADMIN 전용 안내 (MANAGER 이하) ──────────────────────────────────
function AdminOnlyNotice({ feature }: { feature: string }) {
  return (
    <EmptyState
      icon={<ShieldCheck size={36} />}
      title="ADMIN 전용 기능입니다"
      description={`${feature}은(는) 관리자(ADMIN) 권한으로만 조회·변경할 수 있습니다. (§10.1)`}
    />
  )
}

// ── 계정 관리 탭 ────────────────────────────────────────────────────
function AccountsTab({ isAdmin, meId }: { isAdmin: boolean; meId: string }) {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState('')
  const [approveTarget, setApproveTarget] = useState<User | null>(null)
  const [approveRole, setApproveRole] = useState<UserRole>('STAFF')
  const [roleTarget, setRoleTarget] = useState<User | null>(null)
  const [nextRole, setNextRole] = useState<UserRole>('STAFF')
  const [deactivateTarget, setDeactivateTarget] = useState<User | null>(null)
  const [pinResetTarget, setPinResetTarget] = useState<User | null>(null)

  const { data: users = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['users', 'admin-list', statusFilter],
    queryFn: async () => {
      const { data } = await api.get<User[]>('/users', {
        params: statusFilter ? { status: statusFilter } : {},
      })
      return data
    },
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['users'] })
  }

  const approve = useMutation({
    mutationFn: async ({ userId, role }: { userId: string; role: UserRole }) => {
      const { data } = await api.put(`/users/${userId}/approve`, { role })
      return data
    },
    onSuccess: invalidate,
  })
  const changeRole = useMutation({
    mutationFn: async ({ userId, role }: { userId: string; role: UserRole }) => {
      const { data } = await api.put(`/users/${userId}/role`, { role })
      return data
    },
    onSuccess: invalidate,
  })
  const deactivate = useMutation({
    mutationFn: async (userId: string) => {
      const { data } = await api.put(`/users/${userId}/deactivate`)
      return data
    },
    onSuccess: invalidate,
  })
  const pinReset = useMutation({
    mutationFn: async (userId: string) => {
      const { data } = await api.put(`/users/${userId}/pin-reset`)
      return data
    },
    onSuccess: invalidate,
  })

  const pendingCount = useMemo(
    () => users.filter((u) => u.status === 'PENDING').length,
    [users],
  )

  const run = async (fn: () => Promise<unknown>, successMsg: string, cleanup: () => void) => {
    try {
      await fn()
      showToast(successMsg, 'success')
      cleanup()
    } catch (error) {
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '처리에 실패했습니다.', 'danger')
    }
  }

  const columns: Column<User>[] = [
    {
      key: 'user',
      header: '사용자',
      render: (u) => (
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-700 text-xs font-bold text-white">
            {u.name?.charAt(0) ?? '?'}
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-800">
              {u.name ?? '—'}
              {u.user_id === meId && (
                <span className="ml-1 text-[10px] font-normal text-slate-400">(본인)</span>
              )}
            </p>
            <p className="truncate text-xs text-slate-400">{u.email}</p>
          </div>
        </div>
      ),
    },
    {
      key: 'position',
      header: '직급',
      render: (u) => <span className="text-slate-600">{u.position ?? '—'}</span>,
    },
    {
      key: 'role',
      header: '역할',
      render: (u) => (
        <span className="text-sm font-medium text-slate-700">
          {ROLE_LABELS[u.role] ?? u.role}
          <span className="ml-1 text-xs text-slate-400">({u.role})</span>
        </span>
      ),
    },
    {
      key: 'status',
      header: '상태',
      render: (u) => {
        const spec = STATUS_BADGES[u.status] ?? STATUS_BADGES.INACTIVE
        return (
          <span
            className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${spec.cls}`}
          >
            {spec.label}
          </span>
        )
      },
    },
    {
      key: 'pin',
      header: 'PIN',
      render: (u) => (
        <span className={`text-xs ${u.pin_set ? 'text-emerald-600' : 'text-slate-300'}`}>
          {u.pin_set ? '설정됨' : '미설정'}
        </span>
      ),
    },
    {
      key: 'created',
      header: '가입일',
      render: (u) => <span className="text-xs text-slate-400">{fmtDate(u.created_at)}</span>,
    },
    {
      key: 'actions',
      header: '관리',
      className: 'text-right',
      render: (u) => {
        if (!isAdmin) return <span className="text-xs text-slate-300">ADMIN 전용</span>
        return (
          <div className="flex justify-end gap-1">
            {u.status === 'PENDING' && (
              <button
                type="button"
                onClick={() => {
                  setApproveTarget(u)
                  setApproveRole('STAFF')
                }}
                className="rounded-md bg-emerald-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500"
              >
                승인
              </button>
            )}
            {u.status === 'ACTIVE' && u.user_id !== meId && (
              <button
                type="button"
                onClick={() => {
                  setRoleTarget(u)
                  setNextRole(u.role)
                }}
                className="rounded-md border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                역할 변경
              </button>
            )}
            {u.status !== 'INACTIVE' && u.user_id !== meId && (
              <button
                type="button"
                onClick={() => setDeactivateTarget(u)}
                className="rounded-md p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                title="비활성화"
              >
                <Prohibit size={15} />
              </button>
            )}
            {u.pin_set && (
              <button
                type="button"
                onClick={() => setPinResetTarget(u)}
                className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                title="PIN 초기화"
              >
                <LockKeyOpen size={15} />
              </button>
            )}
          </div>
        )
      },
    },
  ]

  return (
    <div className="space-y-3">
      {/* 상태 필터 + 승인 대기 안내 */}
      <div className="flex flex-wrap items-center gap-2">
        {['', 'PENDING', 'ACTIVE', 'INACTIVE'].map((s) => (
          <button
            key={s || 'all'}
            type="button"
            onClick={() => setStatusFilter(s)}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
              statusFilter === s
                ? 'border-slate-800 bg-slate-800 text-white'
                : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
            }`}
          >
            {s === '' ? '전체' : (STATUS_BADGES[s]?.label ?? s)}
          </button>
        ))}
        {pendingCount > 0 && (
          <span className="ml-auto rounded-lg bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700">
            승인 대기 {pendingCount}건
          </span>
        )}
      </div>

      {isError ? (
        <EmptyState
          icon={<UserCircle size={36} />}
          title="사용자 목록을 불러오지 못했습니다"
          description="권한이 없거나 서버에 연결할 수 없습니다."
          action={
            <button
              type="button"
              onClick={() => refetch()}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              다시 시도
            </button>
          }
        />
      ) : (
        <DataTable
          columns={columns}
          rows={users}
          rowKey={(u) => u.user_id}
          isLoading={isLoading}
          emptyTitle="사용자가 없습니다"
          rowClassName={(u) => (u.status === 'INACTIVE' ? 'opacity-50' : '')}
        />
      )}

      {/* 승인 (PENDING→ACTIVE + role 지정) */}
      <Modal
        open={!!approveTarget}
        onClose={() => setApproveTarget(null)}
        title={`가입 승인 — ${approveTarget?.name ?? approveTarget?.email ?? ''}`}
        size="sm"
        footer={
          <>
            <button
              type="button"
              onClick={() => setApproveTarget(null)}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              취소
            </button>
            <button
              type="button"
              disabled={approve.isPending}
              onClick={() =>
                approveTarget &&
                run(
                  () =>
                    approve.mutateAsync({ userId: approveTarget.user_id, role: approveRole }),
                  '가입이 승인되었습니다.',
                  () => setApproveTarget(null),
                )
              }
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-60"
            >
              승인
            </button>
          </>
        }
      >
        <label className="mb-1 block text-xs font-medium text-slate-600">부여할 역할</label>
        <select
          value={approveRole}
          onChange={(e) => setApproveRole(e.target.value as UserRole)}
          className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm focus:border-slate-500 focus:outline-none"
        >
          {(['STAFF', 'MANAGER', 'ADMIN'] as UserRole[]).map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r]} ({r})
            </option>
          ))}
        </select>
      </Modal>

      {/* 역할 변경 */}
      <Modal
        open={!!roleTarget}
        onClose={() => setRoleTarget(null)}
        title={`역할 변경 — ${roleTarget?.name ?? ''}`}
        size="sm"
        footer={
          <>
            <button
              type="button"
              onClick={() => setRoleTarget(null)}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              취소
            </button>
            <button
              type="button"
              disabled={changeRole.isPending}
              onClick={() =>
                roleTarget &&
                run(
                  () => changeRole.mutateAsync({ userId: roleTarget.user_id, role: nextRole }),
                  '역할이 변경되었습니다. 기존 토큰은 즉시 무효화됩니다.',
                  () => setRoleTarget(null),
                )
              }
              className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-60"
            >
              변경
            </button>
          </>
        }
      >
        <select
          value={nextRole}
          onChange={(e) => setNextRole(e.target.value as UserRole)}
          className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm focus:border-slate-500 focus:outline-none"
        >
          {(['STAFF', 'MANAGER', 'ADMIN'] as UserRole[]).map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r]} ({r})
            </option>
          ))}
        </select>
        <p className="mt-2 text-xs text-slate-400">
          역할 변경 시 대상자의 기존 로그인 토큰이 즉시 무효화됩니다 (token_version+1).
        </p>
      </Modal>

      {/* 비활성화 확인 */}
      <ConfirmDialog
        open={!!deactivateTarget}
        title="계정 비활성화"
        message={
          <>
            <b>{deactivateTarget?.name ?? deactivateTarget?.email}</b> 계정을 비활성화합니다.
            즉시 로그인이 차단되며, 기존 토큰도 무효화됩니다.
          </>
        }
        confirmLabel="비활성화"
        danger
        loading={deactivate.isPending}
        onConfirm={() =>
          deactivateTarget &&
          run(
            () => deactivate.mutateAsync(deactivateTarget.user_id),
            '계정이 비활성화되었습니다.',
            () => setDeactivateTarget(null),
          )
        }
        onCancel={() => setDeactivateTarget(null)}
      />

      {/* PIN 초기화 확인 */}
      <ConfirmDialog
        open={!!pinResetTarget}
        title="PIN 초기화"
        message={
          <>
            <b>{pinResetTarget?.name ?? pinResetTarget?.email}</b>의 PIN을 초기화합니다.
            대상자는 다음 로그인 시 PIN을 다시 설정해야 합니다.
          </>
        }
        confirmLabel="초기화"
        loading={pinReset.isPending}
        onConfirm={() =>
          pinResetTarget &&
          run(
            () => pinReset.mutateAsync(pinResetTarget.user_id),
            'PIN이 초기화되었습니다.',
            () => setPinResetTarget(null),
          )
        }
        onCancel={() => setPinResetTarget(null)}
      />
    </div>
  )
}
