// 설정 > 접근 그룹(G3) — 그룹 CRUD·메뉴 매트릭스·구성원 배정·모드 스위치 (ADMIN 전용)
// 그룹=메뉴(화면) 접근 축. 쓰기 권한(직급)은 계정 관리 탭의 역할이 담당 — 두 축 분리.
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleNotch, LockKey, PencilSimple, Plus, Trash } from '@phosphor-icons/react'
import { api } from '../../lib/api/client'
import { Modal } from '../../components/Modal'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useToast } from '../../components/Toast'
import { NAV_GROUPS } from '../../layouts/AppShell/nav'
import { useCodes } from '../../lib/api/queries'
import type { AccessGroupAdmin, AccessGroupMeta, AccessMode, User } from '../../types'

const MODE_LABEL: Record<AccessMode, { label: string; desc: string; cls: string }> = {
  off: { label: '끔', desc: '그룹 제한 없음(전 메뉴)', cls: 'text-slatey' },
  monitor: {
    label: '모니터',
    desc: '차단 없이 위반만 감사 로그 기록',
    cls: 'text-amber-600 dark:text-amber-300',
  },
  enforce: {
    label: '강제',
    desc: '허용 메뉴 밖 화면·API 차단',
    cls: 'text-rose-600 dark:text-rose-300',
  },
}

function useAccessMeta() {
  return useQuery({
    queryKey: ['access-groups', 'meta'],
    queryFn: async () => (await api.get<AccessGroupMeta>('/access-groups/meta')).data,
  })
}

function useAccessGroups() {
  return useQuery({
    queryKey: ['access-groups'],
    queryFn: async () => (await api.get<AccessGroupAdmin[]>('/access-groups')).data,
  })
}

function useInternalUsers() {
  return useQuery({
    queryKey: ['access-groups', 'users'],
    queryFn: async () => {
      const { data } = await api.get<User[]>('/users', { params: { status: 'ACTIVE' } })
      // 외부 포털 역할 제외 — 그룹은 내부 전용
      return data.filter((u) => !['PARTNER', 'INVESTOR'].includes(u.role))
    },
  })
}

interface EditState {
  group?: AccessGroupAdmin // 없으면 신규
  name: string
  dept_code: string // 공통코드 DEPT — 지정 시 이름은 코드 라벨을 따름(부서명 변경은 공통코드 관리에서)
  home_path: string
  memo: string
  menus: Set<string>
  members: Set<string>
}

export function AccessGroupsTab() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const { data: meta } = useAccessMeta()
  const { data: groups = [], isLoading } = useAccessGroups()
  const { data: users = [] } = useInternalUsers()
  const { options: deptOptions } = useCodes('DEPT')

  const [edit, setEdit] = useState<EditState | null>(null)
  const [deleting, setDeleting] = useState<AccessGroupAdmin | null>(null)
  const [confirmEnforce, setConfirmEnforce] = useState(false)

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['access-groups'] })
    queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
  }

  const modeMut = useMutation({
    mutationFn: async (mode: AccessMode) =>
      (await api.put<AccessGroupMeta>('/access-groups/mode', { mode })).data,
    onSuccess: (d) => {
      queryClient.setQueryData(['access-groups', 'meta'], d)
      showToast(`접근제어 모드를 '${MODE_LABEL[d.mode].label}'로 전환했습니다.`, 'success')
    },
    onError: () => showToast('모드 전환에 실패했습니다.', 'danger'),
  })

  const saveMut = useMutation({
    mutationFn: async (st: EditState) => {
      const payload = {
        name: st.name.trim(),
        dept_code: st.dept_code || null,
        home_path: st.home_path,
        memo: st.memo || null,
        menus: Array.from(st.menus),
      }
      const saved = st.group
        ? (await api.put<AccessGroupAdmin>(`/access-groups/${st.group.group_id}`, payload)).data
        : (await api.post<AccessGroupAdmin>('/access-groups', payload)).data
      // 구성원 diff 반영 — 사용자별 그룹 전체 교체 API라, 각 사용자의 타 그룹 소속을 보존해 재계산
      const before = new Set(st.group?.member_ids ?? [])
      const after = st.members
      const changed = [
        ...Array.from(after).filter((id) => !before.has(id)),
        ...Array.from(before).filter((id) => !after.has(id)),
      ]
      const byUser = new Map<string, Set<string>>()
      for (const g of groups) {
        for (const uid of g.member_ids) {
          if (!byUser.has(uid)) byUser.set(uid, new Set())
          byUser.get(uid)!.add(g.group_id)
        }
      }
      for (const uid of changed) {
        const mine = byUser.get(uid) ?? new Set<string>()
        if (after.has(uid)) mine.add(saved.group_id)
        else mine.delete(saved.group_id)
        await api.put(`/access-groups/users/${uid}`, { group_ids: Array.from(mine) })
      }
      return saved
    },
    onSuccess: () => {
      invalidate()
      setEdit(null)
      showToast('그룹을 저장했습니다.', 'success')
    },
    onError: (err) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '그룹 저장에 실패했습니다.', 'danger')
    },
  })

  const deleteMut = useMutation({
    mutationFn: async (groupId: string) => api.delete(`/access-groups/${groupId}`),
    onSuccess: () => {
      invalidate()
      setDeleting(null)
      showToast('그룹을 삭제했습니다.', 'success')
    },
    onError: () => showToast('삭제에 실패했습니다.', 'danger'),
  })

  const openCreate = () =>
    setEdit({ name: '', dept_code: '', home_path: '/dashboard', memo: '', menus: new Set(['/dashboard', '/guide']), members: new Set() })
  const openEdit = (g: AccessGroupAdmin) =>
    setEdit({
      group: g,
      name: g.name,
      dept_code: g.dept_code ?? '',
      home_path: g.home_path ?? '/dashboard',
      memo: g.memo ?? '',
      menus: new Set(g.menus),
      members: new Set(g.member_ids),
    })

  const mode = meta?.mode ?? 'off'

  return (
    <div className="space-y-5">
      {/* 모드 스위치 */}
      <section className="rounded-2xl border border-hairline bg-elevate p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="flex items-center gap-1.5 text-sm font-semibold text-bone">
              <LockKey size={15} weight="fill" />
              접근제어 모드
            </h3>
            <p className="mt-0.5 text-xs text-slatey">
              끔 → 모니터(감사 로그로 영향 확인) → 강제 순서로 전환을 권장합니다. 관리자는 항상
              전체 접근(잠금 방지).
            </p>
          </div>
          <div className="flex rounded-full border border-hairline bg-surface p-0.5">
            {(meta?.modes ?? ['off', 'monitor', 'enforce']).map((m) => (
              <button
                key={m}
                type="button"
                disabled={modeMut.isPending}
                onClick={() => {
                  if (m === 'enforce') setConfirmEnforce(true)
                  else modeMut.mutate(m as AccessMode)
                }}
                className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition-colors ${
                  mode === m ? 'bg-elevate-strong text-bone' : 'text-slatey hover:text-ash'
                }`}
              >
                {MODE_LABEL[m as AccessMode].label}
              </button>
            ))}
          </div>
        </div>
        <p className={`mt-2 text-xs ${MODE_LABEL[mode].cls}`}>
          현재: {MODE_LABEL[mode].label} — {MODE_LABEL[mode].desc}
        </p>
      </section>

      {/* 그룹 목록 */}
      <section>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-bone">접근 그룹</h3>
          <button
            type="button"
            onClick={openCreate}
            className="flex items-center gap-1.5 rounded-full bg-primary px-3.5 py-2 text-sm font-medium text-on-primary hover:opacity-90"
          >
            <Plus size={15} weight="bold" />새 그룹
          </button>
        </div>
        {isLoading ? (
          <p className="flex items-center gap-1.5 text-sm text-ash">
            <CircleNotch size={15} className="animate-spin" />
            불러오는 중…
          </p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-hairline">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead className="bg-elevate text-xs text-ash">
                <tr>
                  <th className="px-3 py-2 font-medium">그룹</th>
                  <th className="px-3 py-2 font-medium">로그인 홈</th>
                  <th className="px-3 py-2 text-right font-medium">메뉴</th>
                  <th className="px-3 py-2 text-right font-medium">구성원</th>
                  <th className="px-3 py-2 font-medium">비고</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {groups.map((g) => (
                  <tr key={g.group_id}>
                    <td className="px-3 py-2 font-medium text-bone">
                      {g.name}
                      {g.is_default && (
                        <span className="ml-1.5 rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] font-bold text-sky-600 dark:text-sky-300">
                          기본
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-slatey">{g.home_path}</td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-bone">
                      {g.menus.length}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-bone">
                      {g.member_ids.length}
                    </td>
                    <td className="max-w-[220px] truncate px-3 py-2 text-xs text-slatey">
                      {g.memo ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        onClick={() => openEdit(g)}
                        className="mr-1 rounded-md border border-hairline p-1.5 text-bone hover:bg-elevate"
                        aria-label="편집"
                      >
                        <PencilSimple size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setDeleting(g)}
                        disabled={g.is_default}
                        className="rounded-md border border-hairline p-1.5 text-rose-400 hover:bg-elevate disabled:opacity-30"
                        aria-label="삭제"
                      >
                        <Trash size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* 편집 모달 — 메뉴 매트릭스 + 구성원 */}
      <Modal
        open={!!edit}
        onClose={() => setEdit(null)}
        title={edit?.group ? `그룹 편집 — ${edit.group.name}` : '새 접근 그룹'}
        size="xl"
        footer={
          edit ? (
            <>
              <button
                type="button"
                onClick={() => setEdit(null)}
                className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
              >
                취소
              </button>
              <button
                type="button"
                disabled={saveMut.isPending || !edit.name.trim()}
                onClick={() => saveMut.mutate(edit)}
                className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
              >
                {saveMut.isPending && <CircleNotch size={15} className="animate-spin" />}
                저장
              </button>
            </>
          ) : undefined
        }
      >
        {edit && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="flex flex-col gap-1 text-xs text-slatey">
                부서 코드(공통코드 DEPT)
                <select
                  value={edit.dept_code}
                  onChange={(e) => {
                    const code = e.target.value
                    const label = deptOptions.find((o) => o.value === code)?.label ?? ''
                    setEdit({ ...edit, dept_code: code, name: code ? label : edit.name })
                  }}
                  className="rounded-lg border border-hairline bg-surface px-2.5 py-1.5 text-sm text-bone"
                >
                  <option value="">— (직접 입력)</option>
                  {deptOptions.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs text-slatey">
                그룹명 *{' '}
                {edit.dept_code && (
                  <span className="text-sky-500">부서 코드 라벨 사용 — 변경은 공통코드 관리에서</span>
                )}
                <input
                  type="text"
                  value={edit.name}
                  disabled={!!edit.dept_code}
                  onChange={(e) => setEdit({ ...edit, name: e.target.value })}
                  className="rounded-lg border border-hairline bg-surface px-2.5 py-1.5 text-sm text-bone disabled:opacity-60"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-slatey">
                로그인 홈(자동 랜딩)
                <select
                  value={edit.home_path}
                  onChange={(e) => setEdit({ ...edit, home_path: e.target.value })}
                  className="rounded-lg border border-hairline bg-surface px-2.5 py-1.5 text-sm text-bone"
                >
                  {NAV_GROUPS.flatMap((g) => g.items).map((i) => (
                    <option key={i.path} value={i.path}>
                      {i.label} ({i.path})
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs text-slatey">
                비고
                <input
                  type="text"
                  value={edit.memo}
                  onChange={(e) => setEdit({ ...edit, memo: e.target.value })}
                  className="rounded-lg border border-hairline bg-surface px-2.5 py-1.5 text-sm text-bone"
                />
              </label>
            </div>

            {/* 메뉴 매트릭스 — nav 그룹별 체크박스. 기본(전사) 그룹은 전 메뉴 고정 */}
            <div>
              <p className="mb-1.5 text-xs font-medium text-ash">
                허용 메뉴{' '}
                {edit.group?.is_default && (
                  <span className="text-sky-500">— 기본 그룹은 전 메뉴 고정(변경 불가)</span>
                )}
              </p>
              <div className="grid grid-cols-1 gap-3 rounded-xl border border-hairline bg-elevate p-3.5 sm:grid-cols-2">
                {NAV_GROUPS.map((navGroup) => (
                  <div key={navGroup.label}>
                    <p className="mb-1 text-[10px] font-bold tracking-wider text-slatey">
                      {navGroup.label}
                    </p>
                    <div className="space-y-1">
                      {navGroup.items.map((item) => (
                        <label
                          key={item.path}
                          className="flex items-center gap-2 text-sm text-bone"
                        >
                          <input
                            type="checkbox"
                            disabled={edit.group?.is_default}
                            checked={edit.menus.has(item.path)}
                            onChange={(e) => {
                              const next = new Set(edit.menus)
                              if (e.target.checked) next.add(item.path)
                              else next.delete(item.path)
                              setEdit({ ...edit, menus: next })
                            }}
                          />
                          {item.label}
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 구성원 — 내부 사용자 배정(1인 다그룹 허용, 미배정=기본 그룹 암묵) */}
            <div>
              <p className="mb-1.5 text-xs font-medium text-ash">
                구성원 ({edit.members.size}명){' '}
                <span className="text-slatey">— 미배정 사용자는 자동으로 기본(전사) 그룹</span>
              </p>
              <div className="grid max-h-[200px] grid-cols-2 gap-1 overflow-y-auto rounded-xl border border-hairline bg-elevate p-3.5 sm:grid-cols-3">
                {users.map((u) => (
                  <label key={u.user_id} className="flex items-center gap-2 text-sm text-bone">
                    <input
                      type="checkbox"
                      checked={edit.members.has(u.user_id)}
                      onChange={(e) => {
                        const next = new Set(edit.members)
                        if (e.target.checked) next.add(u.user_id)
                        else next.delete(u.user_id)
                        setEdit({ ...edit, members: next })
                      }}
                    />
                    <span className="truncate">
                      {u.name || u.email}
                      <span className="ml-1 text-[10px] text-slatey">{u.role}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* 삭제 확인 */}
      <ConfirmDialog
        open={!!deleting}
        title="그룹 삭제"
        message={`'${deleting?.name}' 그룹을 삭제할까요? 소속 ${deleting?.member_ids.length ?? 0}명은 미배정(기본 그룹 권한)으로 돌아갑니다.`}
        confirmLabel="삭제"
        danger
        onConfirm={() => deleting && deleteMut.mutate(deleting.group_id)}
        onCancel={() => setDeleting(null)}
      />

      {/* enforce 전환 확인 */}
      <ConfirmDialog
        open={confirmEnforce}
        title="강제 모드 전환"
        message="허용 메뉴 밖 화면·API가 즉시 차단됩니다. 모니터 모드에서 감사 로그(ACCESS_DENY_WOULD)로 영향이 없는지 확인하셨나요?"
        confirmLabel="강제 전환"
        danger
        onConfirm={() => {
          setConfirmEnforce(false)
          modeMut.mutate('enforce')
        }}
        onCancel={() => setConfirmEnforce(false)}
      />
    </div>
  )
}
