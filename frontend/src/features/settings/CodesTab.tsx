// SCR-14 공통 코드 관리 — 화면에서 추가·수정·비활성 가능한 분류값 (tb_code)
// 첫 대상: 고객사 구분(CLIENT_TYPE). 향후 자산 유형 등도 카테고리로 확장.
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Prohibit, ArrowCounterClockwise, Trash, LockSimple } from '@phosphor-icons/react'
import { DataTable, type Column } from '../../components/DataTable'
import { Modal } from '../../components/Modal'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useToast } from '../../components/Toast'
import { api } from '../../lib/api/client'
import { CODE_PALETTE, PALETTE_ORDER, badgeClassOf } from '../../lib/codePalette'
import type { Code } from '../../types'

// 관리 대상 카테고리 (백엔드 CATEGORY_LABELS와 일치)
const CATEGORIES: { value: string; label: string; hint: string }[] = [
  {
    value: 'CLIENT_TYPE',
    label: '고객사 구분',
    hint: '고객사 마스터 등록 시 선택하는 구분(운수사·건물·농장 등)',
  },
  {
    value: 'CONTRACT_STATUS',
    label: '고객사 계약 상태',
    hint: '고객사 계약 진행 상태(계약중·보류·종료 등). 배지·지도 마커 색상에 반영됩니다.',
  },
  {
    value: 'ACTIVITY_TYPE',
    label: '영업활동 유형',
    hint: '활동 이력 등록 시 선택하는 유형(전화·미팅·현장방문 등).',
  },
  {
    value: 'ASSET_GROUP',
    label: '자산 대분류',
    hint: '자산·수집 계정의 대분류(모빌리티·설비 등).',
  },
  {
    value: 'ASSET_TYPE',
    label: '자산 소분류(연료)',
    hint: '자산 소분류/연료 구분(내연기관·전기차·태양광·히트펌프 등).',
  },
  {
    value: 'ASSET_STATUS',
    label: '자산 운영 상태',
    hint: '자산 운영 상태(운영중·비활성·오류 등).',
  },
]

function extractDetail(error: unknown, fallback: string): string {
  return (
    (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback
  )
}

// 색상 팔레트 선택 — 시맨틱 색상만 선택(임의 hex 금지, 다크/라이트 대응)
function ColorPicker({
  value,
  onChange,
}: {
  value: string
  onChange: (color: string) => void
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {PALETTE_ORDER.map((c) => {
        const selected = value === c
        return (
          <button
            key={c}
            type="button"
            onClick={() => onChange(c)}
            title={CODE_PALETTE[c].label}
            className={`h-7 w-7 rounded-full ${CODE_PALETTE[c].dot} ${
              selected ? 'ring-2 ring-offset-2 ring-offset-graphite ring-white/70' : 'opacity-80 hover:opacity-100'
            }`}
            aria-label={CODE_PALETTE[c].label}
            aria-pressed={selected}
          />
        )
      })}
    </div>
  )
}

export function CodesTab() {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const [category, setCategory] = useState(CATEGORIES[0].value)

  const [createOpen, setCreateOpen] = useState(false)
  const [createForm, setCreateForm] = useState({ code: '', label: '', color: '', sort_order: 0 })
  const [editTarget, setEditTarget] = useState<Code | null>(null)
  const [editForm, setEditForm] = useState({ label: '', color: '', sort_order: 0 })
  const [deleteTarget, setDeleteTarget] = useState<Code | null>(null)

  // 색상 사용 카테고리(상태 배지가 있는 도메인) — CLIENT_TYPE은 색상 미사용
  const usesColor = category !== 'CLIENT_TYPE'

  const activeCategory = CATEGORIES.find((c) => c.value === category) ?? CATEGORIES[0]

  const { data: codes = [], isLoading } = useQuery({
    queryKey: ['codes', category, 'admin'],
    queryFn: async () => {
      const { data } = await api.get<Code[]>('/codes', {
        params: { category, include_inactive: true, with_usage: true },
      })
      return data
    },
  })

  const invalidate = () => {
    // 관리 목록 + 드롭다운 캐시(useCodes) 모두 무효화
    queryClient.invalidateQueries({ queryKey: ['codes'] })
  }

  const createCode = useMutation({
    mutationFn: async (form: typeof createForm) => {
      const { data } = await api.post('/codes', {
        category,
        code: form.code.trim().toUpperCase(),
        label: form.label.trim(),
        color: form.color || null,
        sort_order: form.sort_order,
      })
      return data
    },
    onSuccess: invalidate,
  })
  const updateCode = useMutation({
    mutationFn: async ({ codeId, body }: { codeId: string; body: Record<string, unknown> }) => {
      const { data } = await api.put(`/codes/${codeId}`, body)
      return data
    },
    onSuccess: invalidate,
  })
  const deleteCode = useMutation({
    mutationFn: async (codeId: string) => {
      await api.delete(`/codes/${codeId}`)
    },
    onSuccess: invalidate,
  })

  const run = async (fn: () => Promise<unknown>, ok: string, cleanup: () => void) => {
    try {
      await fn()
      showToast(ok, 'success')
      cleanup()
    } catch (error) {
      showToast(extractDetail(error, '처리에 실패했습니다.'), 'danger')
    }
  }

  const toggleActive = (c: Code) =>
    run(
      () => updateCode.mutateAsync({ codeId: c.code_id, body: { active: c.active === 'Y' ? 'N' : 'Y' } }),
      c.active === 'Y' ? '비활성으로 전환했습니다.' : '활성으로 전환했습니다.',
      () => undefined,
    )

  const columns: Column<Code>[] = [
    {
      key: 'label',
      header: '표시명',
      render: (c) => (
        <span className="inline-flex items-center gap-2 font-semibold text-bone">
          {usesColor && (
            <span
              className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${badgeClassOf(c.color)}`}
            >
              {c.label}
            </span>
          )}
          {!usesColor && c.label}
          {c.is_locked && (
            <span
              className="inline-flex items-center gap-0.5 rounded bg-elevate-strong px-1.5 py-0.5 text-[10px] font-medium text-slatey"
              title="시스템 로직이 참조하는 코드 — 표시명·색상만 변경 가능"
            >
              <LockSimple size={10} weight="fill" /> 잠금
            </span>
          )}
          {!c.is_locked && c.is_system === 'Y' && (
            <span className="rounded bg-elevate-strong px-1.5 py-0.5 text-[10px] font-medium text-slatey">
              내장
            </span>
          )}
        </span>
      ),
    },
    {
      key: 'code',
      header: '코드값',
      render: (c) => <span className="font-mono text-xs text-ash">{c.code}</span>,
    },
    {
      key: 'usage',
      header: '사용 중',
      render: (c) => (
        <span className="text-xs text-ash">{(c.usage_count ?? 0).toLocaleString()}건</span>
      ),
    },
    {
      key: 'sort',
      header: '정렬',
      render: (c) => <span className="text-xs text-slatey">{c.sort_order}</span>,
    },
    {
      key: 'active',
      header: '상태',
      render: (c) => (
        <span
          className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${
            c.active === 'Y'
              ? 'border-emerald-400/25 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
              : 'border-hairline bg-elevate-strong text-ash'
          }`}
        >
          {c.active === 'Y' ? '활성' : '비활성'}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '관리',
      className: 'text-right',
      render: (c) => (
        <div className="flex justify-end gap-1">
          <button
            type="button"
            onClick={() => {
              setEditTarget(c)
              setEditForm({ label: c.label, color: c.color ?? '', sort_order: c.sort_order })
            }}
            className="rounded-full border border-hairline px-2.5 py-1.5 text-xs font-medium text-bone hover:bg-elevate"
          >
            편집
          </button>
          {/* 로직 참조 코드는 비활성·삭제 불가(라벨·색상만) */}
          {!c.is_locked && (
            <button
              type="button"
              onClick={() => toggleActive(c)}
              className="rounded-lg p-1.5 text-smoke hover:bg-elevate hover:text-bone"
              title={c.active === 'Y' ? '비활성으로 전환' : '활성으로 전환'}
            >
              {c.active === 'Y' ? <Prohibit size={15} /> : <ArrowCounterClockwise size={15} />}
            </button>
          )}
          {!c.is_locked && c.is_system !== 'Y' && (
            <button
              type="button"
              onClick={() => setDeleteTarget(c)}
              className="rounded-lg p-1.5 text-smoke hover:bg-rose-500/10 hover:text-rose-700 dark:text-rose-300"
              title="삭제"
            >
              <Trash size={15} />
            </button>
          )}
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="h-9 rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone focus:border-white/30 focus:outline-none"
        >
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => {
            setCreateForm({ code: '', label: '', color: '', sort_order: (codes.length + 1) * 10 })
            setCreateOpen(true)
          }}
          className="ml-auto rounded-full bg-primary px-3.5 py-1.5 text-xs font-medium text-on-primary hover:opacity-90"
        >
          ＋ 코드 추가
        </button>
      </div>

      <p className="rounded-lg border border-hairline bg-elevate px-3 py-2 text-xs leading-relaxed text-ash">
        {activeCategory.hint}
        <br />
        코드값은 생성 후 변경할 수 없습니다(기존 데이터 보호). 표시명은 언제든 수정
        가능합니다. 사용 중인 코드는 삭제할 수 없으니 <b>비활성</b>으로 전환하세요 — 신규
        선택에서만 숨겨지고 기존 데이터는 그대로 유지됩니다.
      </p>

      <DataTable
        columns={columns}
        rows={codes}
        rowKey={(c) => c.code_id}
        isLoading={isLoading}
        emptyTitle="등록된 코드가 없습니다"
        rowClassName={(c) => (c.active === 'Y' ? '' : 'opacity-55')}
      />

      {/* 코드 추가 */}
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title={`${activeCategory.label} 추가`}>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-ash">
              코드값<span className="ml-0.5 text-rose-500">*</span>
              <span className="ml-1 font-normal text-slatey">영문 대문자·숫자·_ (변경 불가)</span>
            </label>
            <input
              value={createForm.code}
              onChange={(e) =>
                setCreateForm((f) => ({
                  ...f,
                  code: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ''),
                }))
              }
              placeholder="예: FARM"
              className="h-10 w-full rounded-lg border border-hairline bg-graphite px-3 font-mono text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ash">
              표시명<span className="ml-0.5 text-rose-500">*</span>
            </label>
            <input
              value={createForm.label}
              onChange={(e) => setCreateForm((f) => ({ ...f, label: e.target.value }))}
              placeholder="예: 농장"
              className="h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
            />
          </div>
          {usesColor && (
            <div>
              <label className="mb-1.5 block text-xs font-medium text-ash">배지 색상</label>
              <ColorPicker
                value={createForm.color}
                onChange={(color) => setCreateForm((f) => ({ ...f, color }))}
              />
            </div>
          )}
          <div>
            <label className="mb-1 block text-xs font-medium text-ash">정렬 순서</label>
            <input
              type="number"
              value={createForm.sort_order}
              onChange={(e) => setCreateForm((f) => ({ ...f, sort_order: Number(e.target.value) }))}
              className="h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone focus:border-white/30 focus:outline-none"
            />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={() => setCreateOpen(false)}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
            >
              취소
            </button>
            <button
              type="button"
              disabled={!createForm.code.trim() || !createForm.label.trim() || createCode.isPending}
              onClick={() =>
                run(
                  () => createCode.mutateAsync(createForm),
                  '코드가 추가되었습니다.',
                  () => setCreateOpen(false),
                )
              }
              className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
            >
              추가
            </button>
          </div>
        </div>
      </Modal>

      {/* 코드 편집 (표시명·정렬) */}
      <Modal open={!!editTarget} onClose={() => setEditTarget(null)} title="코드 수정">
        {editTarget && (
          <div className="space-y-3">
            <p className="text-xs text-slatey">
              코드값 <span className="font-mono text-ash">{editTarget.code}</span> (변경 불가)
            </p>
            <div>
              <label className="mb-1 block text-xs font-medium text-ash">표시명</label>
              <input
                value={editForm.label}
                onChange={(e) => setEditForm((f) => ({ ...f, label: e.target.value }))}
                className="h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone focus:border-white/30 focus:outline-none"
              />
            </div>
            {usesColor && (
              <div>
                <label className="mb-1.5 block text-xs font-medium text-ash">배지 색상</label>
                <ColorPicker
                  value={editForm.color}
                  onChange={(color) => setEditForm((f) => ({ ...f, color }))}
                />
              </div>
            )}
            <div>
              <label className="mb-1 block text-xs font-medium text-ash">정렬 순서</label>
              <input
                type="number"
                value={editForm.sort_order}
                onChange={(e) => setEditForm((f) => ({ ...f, sort_order: Number(e.target.value) }))}
                className="h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone focus:border-white/30 focus:outline-none"
              />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setEditTarget(null)}
                className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
              >
                취소
              </button>
              <button
                type="button"
                disabled={!editForm.label.trim() || updateCode.isPending}
                onClick={() =>
                  run(
                    () =>
                      updateCode.mutateAsync({
                        codeId: editTarget.code_id,
                        body: {
                          label: editForm.label.trim(),
                          color: editForm.color || null,
                          sort_order: editForm.sort_order,
                        },
                      }),
                    '코드가 수정되었습니다.',
                    () => setEditTarget(null),
                  )
                }
                className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
              >
                저장
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* 삭제 확인 */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="코드 삭제"
        message={
          <>
            <b>{deleteTarget?.label}</b> ({deleteTarget?.code}) 코드를 삭제합니다. 사용 중인
            코드는 삭제되지 않으며, 이 경우 비활성 전환을 이용하세요.
          </>
        }
        confirmLabel="삭제"
        danger
        loading={deleteCode.isPending}
        onConfirm={() =>
          deleteTarget &&
          run(
            () => deleteCode.mutateAsync(deleteTarget.code_id),
            '코드가 삭제되었습니다.',
            () => setDeleteTarget(null),
          )
        }
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
