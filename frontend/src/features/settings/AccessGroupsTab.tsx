// 설정 > 접근 그룹(G3) — 그룹 CRUD·메뉴 매트릭스·구성원 배정·모드 스위치 (ADMIN 전용)
// 그룹=메뉴(화면) 접근 축. 쓰기 권한(직급)은 계정 관리 탭의 역할이 담당 — 두 축 분리.
// UX: 마스터-디테일(좌 그룹 목록/우 상세 인라인 편집) + 구성원별 보기(사람 기준 배정).
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CircleNotch,
  LockKey,
  MagnifyingGlass,
  Plus,
  Trash,
  UsersThree,
  SquaresFour,
  X,
} from '@phosphor-icons/react'
import { api } from '../../lib/api/client'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useToast } from '../../components/Toast'
import { NAV_GROUPS } from '../../layouts/AppShell/nav'
import { useCodes } from '../../lib/api/queries'
import type { AccessGroupAdmin, AccessGroupMeta, AccessMode, User } from '../../types'

const MODE_LABEL: Record<AccessMode, { label: string; desc: string; cls: string }> = {
  off: { label: '끔', desc: 'API 차단 없음', cls: 'text-slatey' },
  monitor: {
    label: '모니터',
    desc: 'API 차단 없이 위반만 감사 로그 기록',
    cls: 'text-amber-600 dark:text-amber-300',
  },
  enforce: {
    label: '강제',
    desc: '허용 메뉴 밖 API 403 차단',
    cls: 'text-rose-600 dark:text-rose-300',
  },
}

const ALL_NAV_ITEMS = NAV_GROUPS.flatMap((g) => g.items)
const MENU_LABEL = new Map(ALL_NAV_ITEMS.map((i) => [i.path, i.label]))

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

/** 이름·이메일·직급 통합 검색(공백 무시, 대소문자 무시) */
function matchUser(u: User, q: string): boolean {
  if (!q) return true
  const hay = `${u.name} ${u.email} ${u.position ?? ''} ${u.role}`.toLowerCase()
  return q
    .toLowerCase()
    .split(/\s+/)
    .every((t) => hay.includes(t))
}

interface EditState {
  name: string
  dept_code: string // 공통코드 DEPT — 지정 시 이름은 코드 라벨을 따름(부서명 변경은 공통코드 관리에서)
  home_path: string
  memo: string
  menus: Set<string>
  members: Set<string>
}

function toEditState(g?: AccessGroupAdmin): EditState {
  return g
    ? {
        name: g.name,
        dept_code: g.dept_code ?? '',
        home_path: g.home_path ?? '/dashboard',
        memo: g.memo ?? '',
        menus: new Set(g.menus),
        members: new Set(g.member_ids),
      }
    : {
        name: '',
        dept_code: '',
        home_path: '/dashboard',
        memo: '',
        menus: new Set(['/dashboard', '/guide']),
        members: new Set(),
      }
}

function isDirty(st: EditState, g?: AccessGroupAdmin): boolean {
  const base = toEditState(g)
  const setEq = (a: Set<string>, b: Set<string>) =>
    a.size === b.size && Array.from(a).every((x) => b.has(x))
  return (
    st.name !== base.name ||
    st.dept_code !== base.dept_code ||
    st.home_path !== base.home_path ||
    st.memo !== base.memo ||
    !setEq(st.menus, base.menus) ||
    !setEq(st.members, base.members)
  )
}

export function AccessGroupsTab() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const { data: meta } = useAccessMeta()
  const { data: groups = [], isLoading } = useAccessGroups()
  const { data: users = [] } = useInternalUsers()

  const [view, setView] = useState<'groups' | 'members'>('groups')
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
          현재: {MODE_LABEL[mode].label} — {MODE_LABEL[mode].desc} · 메뉴 표시는 모드와 무관하게
          그룹 설정을 항상 따릅니다(재로그인·새로고침 시 반영)
        </p>
      </section>

      {/* 보기 전환 — 그룹 기준 / 사람 기준 */}
      <div className="flex items-center gap-1 rounded-full border border-hairline bg-elevate p-0.5 w-fit">
        {(
          [
            { key: 'groups', label: '그룹별 설정', icon: SquaresFour },
            { key: 'members', label: '구성원별 보기', icon: UsersThree },
          ] as const
        ).map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setView(t.key)}
            className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-semibold transition-colors ${
              view === t.key ? 'bg-elevate-strong text-bone' : 'text-slatey hover:text-ash'
            }`}
          >
            <t.icon size={14} />
            {t.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className="flex items-center gap-1.5 text-sm text-ash">
          <CircleNotch size={15} className="animate-spin" />
          불러오는 중…
        </p>
      ) : view === 'groups' ? (
        <GroupsView groups={groups} users={users} onChanged={invalidate} />
      ) : (
        <MembersView groups={groups} users={users} onChanged={invalidate} />
      )}

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

// ── 그룹별 설정 — 마스터(좌 목록)·디테일(우 인라인 편집) ─────────────────────────

function GroupsView({
  groups,
  users,
  onChanged,
}: {
  groups: AccessGroupAdmin[]
  users: User[]
  onChanged: () => void
}) {
  const { showToast } = useToast()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<AccessGroupAdmin | null>(null)

  // 최초/삭제 후 자동 선택 — 첫 그룹
  const selected = creating ? undefined : (groups.find((g) => g.group_id === selectedId) ?? groups[0])
  useEffect(() => {
    if (!creating && !selectedId && groups[0]) setSelectedId(groups[0].group_id)
  }, [creating, selectedId, groups])

  const deleteMut = useMutation({
    mutationFn: async (groupId: string) => api.delete(`/access-groups/${groupId}`),
    onSuccess: () => {
      onChanged()
      setDeleting(null)
      setSelectedId(null)
      showToast('그룹을 삭제했습니다.', 'success')
    },
    onError: () => showToast('삭제에 실패했습니다.', 'danger'),
  })

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[260px_1fr]">
      {/* 좌: 그룹 목록 */}
      <div className="space-y-2">
        <button
          type="button"
          onClick={() => {
            setCreating(true)
            setSelectedId(null)
          }}
          className={`flex w-full items-center justify-center gap-1.5 rounded-xl border px-3.5 py-2.5 text-sm font-medium transition-colors ${
            creating
              ? 'border-primary bg-primary text-on-primary'
              : 'border-dashed border-hairline text-slatey hover:border-primary hover:text-bone'
          }`}
        >
          <Plus size={15} weight="bold" />새 그룹 만들기
        </button>
        {groups.map((g) => {
          const active = !creating && selected?.group_id === g.group_id
          return (
            <button
              key={g.group_id}
              type="button"
              onClick={() => {
                setCreating(false)
                setSelectedId(g.group_id)
              }}
              className={`block w-full rounded-xl border px-3.5 py-2.5 text-left transition-colors ${
                active
                  ? 'border-primary/60 bg-elevate-strong'
                  : 'border-hairline bg-elevate hover:bg-elevate-strong'
              }`}
            >
              <p className="flex items-center gap-1.5 text-sm font-semibold text-bone">
                <span className="truncate">{g.name}</span>
                {g.is_default && (
                  <span className="shrink-0 rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] font-bold text-sky-600 dark:text-sky-300">
                    기본
                  </span>
                )}
              </p>
              <p className="mt-0.5 text-[11px] text-slatey">
                구성원 {g.member_ids.length}명 · 메뉴 {g.is_default ? '전체' : `${g.menus.length}개`}
              </p>
            </button>
          )
        })}
        <p className="px-1 text-[11px] leading-relaxed text-slatey">
          그룹에 배정되지 않은 사용자는 자동으로 <b>기본(전사) 그룹</b> 권한(전 메뉴)입니다. 한
          사람이 여러 그룹이면 허용 메뉴는 합집합.
        </p>
      </div>

      {/* 우: 상세 편집 */}
      {creating || selected ? (
        <GroupDetail
          key={creating ? '__new__' : selected!.group_id}
          group={creating ? undefined : selected}
          groups={groups}
          users={users}
          onSaved={(id) => {
            setCreating(false)
            setSelectedId(id)
            onChanged()
          }}
          onCancelCreate={creating ? () => setCreating(false) : undefined}
          onDelete={selected && !selected.is_default ? () => setDeleting(selected) : undefined}
        />
      ) : (
        <div className="rounded-2xl border border-dashed border-hairline p-8 text-center text-sm text-slatey">
          왼쪽에서 그룹을 선택하거나 새 그룹을 만드세요.
        </div>
      )}

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
    </div>
  )
}

function GroupDetail({
  group,
  groups,
  users,
  onSaved,
  onCancelCreate,
  onDelete,
}: {
  group?: AccessGroupAdmin // 없으면 신규
  groups: AccessGroupAdmin[]
  users: User[]
  onSaved: (groupId: string) => void
  onCancelCreate?: () => void
  onDelete?: () => void
}) {
  const { showToast } = useToast()
  const { options: deptOptions } = useCodes('DEPT')
  const [st, setSt] = useState<EditState>(() => toEditState(group))
  const dirty = isDirty(st, group)

  const saveMut = useMutation({
    mutationFn: async () => {
      const payload = {
        name: st.name.trim(),
        dept_code: st.dept_code || null,
        home_path: st.home_path,
        memo: st.memo || null,
        menus: Array.from(st.menus),
      }
      const saved = group
        ? (await api.put<AccessGroupAdmin>(`/access-groups/${group.group_id}`, payload)).data
        : (await api.post<AccessGroupAdmin>('/access-groups', payload)).data
      // 구성원 diff 반영 — 사용자별 그룹 전체 교체 API라, 각 사용자의 타 그룹 소속을 보존해 재계산
      const before = new Set(group?.member_ids ?? [])
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
    onSuccess: (saved) => {
      showToast('그룹을 저장했습니다.', 'success')
      onSaved(saved.group_id)
    },
    onError: (err) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '그룹 저장에 실패했습니다.', 'danger')
    },
  })

  return (
    <div className="space-y-4 rounded-2xl border border-hairline bg-elevate p-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-sm font-semibold text-bone">
          {group ? `그룹 편집 — ${group.name}` : '새 접근 그룹'}
        </h3>
        {onDelete && (
          <button
            type="button"
            onClick={onDelete}
            className="flex items-center gap-1 rounded-md border border-hairline px-2 py-1 text-xs text-rose-500 hover:bg-elevate-strong dark:text-rose-300"
          >
            <Trash size={13} />
            그룹 삭제
          </button>
        )}
      </div>

      {/* ① 기본 정보 */}
      <section>
        <p className="mb-1.5 text-xs font-semibold text-ash">① 기본 정보</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-1 text-xs text-slatey">
            부서 코드(공통코드 DEPT)
            <select
              value={st.dept_code}
              onChange={(e) => {
                const code = e.target.value
                const label = deptOptions.find((o) => o.value === code)?.label ?? ''
                setSt({ ...st, dept_code: code, name: code ? label : st.name })
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
            {st.dept_code && (
              <span className="text-sky-500">부서 코드 라벨 사용 — 변경은 공통코드 관리에서</span>
            )}
            <input
              type="text"
              value={st.name}
              disabled={!!st.dept_code}
              onChange={(e) => setSt({ ...st, name: e.target.value })}
              className="rounded-lg border border-hairline bg-surface px-2.5 py-1.5 text-sm text-bone disabled:opacity-60"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slatey">
            로그인 홈(자동 랜딩)
            <select
              value={st.home_path}
              onChange={(e) => setSt({ ...st, home_path: e.target.value })}
              className="rounded-lg border border-hairline bg-surface px-2.5 py-1.5 text-sm text-bone"
            >
              {ALL_NAV_ITEMS.map((i) => (
                <option key={i.path} value={i.path}>
                  {i.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-slatey">
            비고
            <input
              type="text"
              value={st.memo}
              onChange={(e) => setSt({ ...st, memo: e.target.value })}
              className="rounded-lg border border-hairline bg-surface px-2.5 py-1.5 text-sm text-bone"
            />
          </label>
        </div>
      </section>

      {/* ② 허용 메뉴 — nav 섹션별 전체 토글 + 카운트 */}
      <section>
        <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs font-semibold text-ash">
            ② 허용 메뉴{' '}
            <span className="font-mono text-slatey">
              {group?.is_default ? '전체 고정' : `${st.menus.size}/${ALL_NAV_ITEMS.length}`}
            </span>{' '}
            {group?.is_default && (
              <span className="text-sky-500">— 기본 그룹은 전 메뉴 고정(변경 불가)</span>
            )}
          </p>
          {!group?.is_default && (
            <div className="flex gap-1.5">
              <button
                type="button"
                onClick={() => setSt({ ...st, menus: new Set(ALL_NAV_ITEMS.map((i) => i.path)) })}
                className="rounded-full border border-hairline px-2.5 py-1 text-[11px] text-slatey hover:text-bone"
              >
                전체 선택
              </button>
              <button
                type="button"
                onClick={() => setSt({ ...st, menus: new Set() })}
                className="rounded-full border border-hairline px-2.5 py-1 text-[11px] text-slatey hover:text-bone"
              >
                전체 해제
              </button>
            </div>
          )}
        </div>
        <div className="grid grid-cols-1 gap-3 rounded-xl border border-hairline bg-surface p-3.5 sm:grid-cols-2 lg:grid-cols-3">
          {NAV_GROUPS.map((navGroup) => {
            const paths = navGroup.items.map((i) => i.path)
            const checkedCount = paths.filter((p) => st.menus.has(p)).length
            const all = checkedCount === paths.length
            return (
              <div key={navGroup.label}>
                <label className="mb-1 flex items-center gap-1.5 text-[10px] font-bold tracking-wider text-slatey">
                  <input
                    type="checkbox"
                    disabled={group?.is_default}
                    checked={all}
                    ref={(el) => {
                      if (el) el.indeterminate = checkedCount > 0 && !all
                    }}
                    onChange={(e) => {
                      const next = new Set(st.menus)
                      for (const p of paths) {
                        if (e.target.checked) next.add(p)
                        else next.delete(p)
                      }
                      setSt({ ...st, menus: next })
                    }}
                  />
                  {navGroup.label}
                </label>
                <div className="space-y-1 pl-0.5">
                  {navGroup.items.map((item) => (
                    <label key={item.path} className="flex items-center gap-2 text-sm text-bone">
                      <input
                        type="checkbox"
                        disabled={group?.is_default}
                        checked={st.menus.has(item.path)}
                        onChange={(e) => {
                          const next = new Set(st.menus)
                          if (e.target.checked) next.add(item.path)
                          else next.delete(item.path)
                          setSt({ ...st, menus: next })
                        }}
                      />
                      {item.label}
                    </label>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* ③ 구성원 — 검색 + 선택 칩 + 후보 리스트 */}
      <MemberPicker
        users={users}
        selected={st.members}
        onChange={(members) => setSt({ ...st, members })}
      />

      {/* 저장 바 */}
      <div className="flex items-center justify-end gap-2 border-t border-hairline pt-3">
        {dirty && <span className="mr-auto text-[11px] text-amber-600 dark:text-amber-300">저장되지 않은 변경이 있습니다</span>}
        {onCancelCreate && (
          <button
            type="button"
            onClick={onCancelCreate}
            className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate-strong"
          >
            취소
          </button>
        )}
        {group && dirty && (
          <button
            type="button"
            onClick={() => setSt(toEditState(group))}
            className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate-strong"
          >
            변경 취소
          </button>
        )}
        <button
          type="button"
          disabled={saveMut.isPending || !st.name.trim() || (!!group && !dirty)}
          onClick={() => saveMut.mutate()}
          className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
        >
          {saveMut.isPending && <CircleNotch size={15} className="animate-spin" />}
          저장
        </button>
      </div>
    </div>
  )
}

/** 구성원 선택 — 검색(이름·이메일·직급) + 선택 칩(×제거) + 후보 클릭 추가 */
function MemberPicker({
  users,
  selected,
  onChange,
}: {
  users: User[]
  selected: Set<string>
  onChange: (next: Set<string>) => void
}) {
  const [q, setQ] = useState('')
  const byId = useMemo(() => new Map(users.map((u) => [u.user_id, u])), [users])
  const candidates = users.filter((u) => !selected.has(u.user_id) && matchUser(u, q))

  const add = (id: string) => {
    const next = new Set(selected)
    next.add(id)
    onChange(next)
  }
  const remove = (id: string) => {
    const next = new Set(selected)
    next.delete(id)
    onChange(next)
  }

  return (
    <section>
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold text-ash">
          ③ 구성원 <span className="font-mono text-slatey">{selected.size}명</span>{' '}
          <span className="font-normal text-slatey">— 미배정 사용자는 자동으로 기본(전사) 그룹</span>
        </p>
        <label className="relative">
          <MagnifyingGlass
            size={13}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slatey"
          />
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="이름·이메일·직급 검색"
            className="w-52 rounded-full border border-hairline bg-surface py-1.5 pl-7 pr-3 text-xs text-bone"
          />
        </label>
      </div>
      <div className="rounded-xl border border-hairline bg-surface p-3">
        {/* 선택된 구성원 칩 */}
        {selected.size > 0 ? (
          <div className="mb-2.5 flex flex-wrap gap-1.5 border-b border-hairline pb-2.5">
            {Array.from(selected).map((id) => {
              const u = byId.get(id)
              return (
                <span
                  key={id}
                  className="flex items-center gap-1 rounded-full bg-elevate-strong px-2.5 py-1 text-xs text-bone"
                >
                  {u ? u.name || u.email : id}
                  {u?.position && <span className="text-[10px] text-slatey">{u.position}</span>}
                  <button
                    type="button"
                    onClick={() => remove(id)}
                    aria-label="구성원 제외"
                    className="ml-0.5 rounded-full text-slatey hover:text-rose-500"
                  >
                    <X size={11} weight="bold" />
                  </button>
                </span>
              )
            })}
          </div>
        ) : (
          <p className="mb-2.5 border-b border-hairline pb-2.5 text-xs text-slatey">
            아직 배정된 구성원이 없습니다 — 아래 목록에서 클릭해 추가하세요.
          </p>
        )}
        {/* 후보 목록 */}
        <div className="grid max-h-[180px] grid-cols-1 gap-0.5 overflow-y-auto sm:grid-cols-2 lg:grid-cols-3">
          {candidates.map((u) => (
            <button
              key={u.user_id}
              type="button"
              onClick={() => add(u.user_id)}
              className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-sm text-bone hover:bg-elevate-strong"
            >
              <Plus size={12} weight="bold" className="shrink-0 text-slatey" />
              <span className="truncate">
                {u.name || u.email}
                <span className="ml-1 text-[10px] text-slatey">
                  {u.position ? `${u.position} · ` : ''}
                  {u.role}
                </span>
              </span>
            </button>
          ))}
          {candidates.length === 0 && (
            <p className="col-span-full px-2 py-1.5 text-xs text-slatey">
              {q ? '검색 결과가 없습니다.' : '추가할 수 있는 사용자가 없습니다.'}
            </p>
          )}
        </div>
      </div>
    </section>
  )
}

// ── 구성원별 보기 — 사람 기준으로 소속 그룹 확인·변경 ───────────────────────────

function MembersView({
  groups,
  users,
  onChanged,
}: {
  groups: AccessGroupAdmin[]
  users: User[]
  onChanged: () => void
}) {
  const { showToast } = useToast()
  const [q, setQ] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState<Set<string>>(new Set())

  const groupsOfUser = useMemo(() => {
    const m = new Map<string, string[]>()
    for (const g of groups) for (const uid of g.member_ids) m.set(uid, [...(m.get(uid) ?? []), g.group_id])
    return m
  }, [groups])
  const groupById = useMemo(() => new Map(groups.map((g) => [g.group_id, g])), [groups])

  const saveMut = useMutation({
    mutationFn: async ({ userId, groupIds }: { userId: string; groupIds: string[] }) =>
      api.put(`/access-groups/users/${userId}`, { group_ids: groupIds }),
    onSuccess: () => {
      onChanged()
      setEditingId(null)
      showToast('소속 그룹을 저장했습니다.', 'success')
    },
    onError: () => showToast('저장에 실패했습니다.', 'danger'),
  })

  const filtered = users.filter((u) => matchUser(u, q))
  const assignable = groups.filter((g) => !g.is_default) // 기본 그룹은 암묵 상속 — 명시 배정 대상 아님

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-slatey">
          사람 기준으로 소속 그룹을 확인·변경합니다. 아무 그룹에도 없으면{' '}
          <b>기본(전사) 그룹 권한(전 메뉴)</b>입니다.
        </p>
        <label className="relative">
          <MagnifyingGlass
            size={13}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slatey"
          />
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="이름·이메일·직급 검색"
            className="w-56 rounded-full border border-hairline bg-surface py-1.5 pl-7 pr-3 text-xs text-bone"
          />
        </label>
      </div>
      <div className="overflow-x-auto rounded-xl border border-hairline">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="bg-elevate text-xs text-ash">
            <tr>
              <th className="px-3 py-2 font-medium">이름</th>
              <th className="px-3 py-2 font-medium">역할</th>
              <th className="px-3 py-2 font-medium">소속 그룹</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {filtered.map((u) => {
              const mine = groupsOfUser.get(u.user_id) ?? []
              const editing = editingId === u.user_id
              return (
                <tr key={u.user_id} className="align-top">
                  <td className="px-3 py-2">
                    <span className="font-medium text-bone">{u.name || u.email}</span>
                    {u.position && <span className="ml-1.5 text-[11px] text-slatey">{u.position}</span>}
                  </td>
                  <td className="px-3 py-2 text-xs text-slatey">{u.role}</td>
                  <td className="px-3 py-2">
                    {editing ? (
                      <div className="flex flex-wrap gap-x-4 gap-y-1">
                        {assignable.map((g) => (
                          <label key={g.group_id} className="flex items-center gap-1.5 text-xs text-bone">
                            <input
                              type="checkbox"
                              checked={draft.has(g.group_id)}
                              onChange={(e) => {
                                const next = new Set(draft)
                                if (e.target.checked) next.add(g.group_id)
                                else next.delete(g.group_id)
                                setDraft(next)
                              }}
                            />
                            {g.name}
                          </label>
                        ))}
                        {assignable.length === 0 && (
                          <span className="text-xs text-slatey">배정 가능한 그룹이 없습니다.</span>
                        )}
                      </div>
                    ) : mine.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {mine.map((gid) => (
                          <span
                            key={gid}
                            className="rounded-full bg-elevate-strong px-2 py-0.5 text-[11px] text-bone"
                          >
                            {groupById.get(gid)?.name ?? gid}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-[11px] text-slatey">미배정 — 기본(전사) 그룹</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {editing ? (
                      <>
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          className="mr-1 rounded-full border border-hairline px-2.5 py-1 text-xs text-bone hover:bg-elevate"
                        >
                          취소
                        </button>
                        <button
                          type="button"
                          disabled={saveMut.isPending}
                          onClick={() =>
                            saveMut.mutate({ userId: u.user_id, groupIds: Array.from(draft) })
                          }
                          className="rounded-full bg-primary px-2.5 py-1 text-xs font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
                        >
                          저장
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setEditingId(u.user_id)
                          setDraft(new Set(mine.filter((gid) => !groupById.get(gid)?.is_default)))
                        }}
                        className="rounded-full border border-hairline px-2.5 py-1 text-xs text-bone hover:bg-elevate"
                      >
                        그룹 변경
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-xs text-slatey">
                  검색 결과가 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
