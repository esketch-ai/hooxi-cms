// INC-8a 매수자(투자·금융사) 마스터 — 목록·검색·등록/수정·삭제 (고객사 마스터 톤 준용)
import { useMemo, useState } from 'react'
import { Bank, PencilSimple, Plus, Trash } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { FilterBar, FilterSearch } from '../../components/FilterBar'
import { DataTable, type Column } from '../../components/DataTable'
import { Pagination } from '../../components/Pagination'
import { EmptyState } from '../../components/EmptyState'
import { Modal } from '../../components/Modal'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useToast } from '../../components/Toast'
import { useCodes } from '../../lib/api/queries'
import { fmtServerDate } from '../../lib/format'
import { useBuyers, useSaveBuyer, useDeleteBuyer } from './api'
import type { Buyer, BuyerPayload } from './types'

const PAGE_SIZE = 20

const EMPTY_FORM: BuyerPayload = {
  name: '',
  buyer_type: '',
  biz_reg_no: '',
  contact_name: '',
  contact_phone: '',
  contact_email: '',
  memo: '',
}

const inputCls =
  'h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none'

export function BuyersPage() {
  const { showToast } = useToast()
  const { options: buyerTypeOptions, labelOf: buyerTypeLabel } = useCodes('SALE_BUYER_TYPE')

  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Buyer | null>(null)
  const [form, setForm] = useState<BuyerPayload>(EMPTY_FORM)
  const [deleteTarget, setDeleteTarget] = useState<Buyer | null>(null)

  const filters = useMemo(
    () => ({ search, page, page_size: PAGE_SIZE }),
    [search, page],
  )

  const { data, isLoading, isError, refetch } = useBuyers(filters)
  const rows = data?.items ?? []
  const total = data?.total ?? 0

  const save = useSaveBuyer(editing?.buyer_id)
  const remove = useDeleteBuyer()

  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY_FORM)
    setFormOpen(true)
  }
  const openEdit = (b: Buyer) => {
    setEditing(b)
    setForm({
      name: b.name ?? '',
      buyer_type: b.buyer_type ?? '',
      biz_reg_no: b.biz_reg_no ?? '',
      contact_name: b.contact_name ?? '',
      contact_phone: b.contact_phone ?? '',
      contact_email: b.contact_email ?? '',
      memo: b.memo ?? '',
    })
    setFormOpen(true)
  }

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

  const submit = () => {
    const payload: BuyerPayload = {
      name: form.name.trim(),
      buyer_type: form.buyer_type?.trim() || null,
      biz_reg_no: form.biz_reg_no?.trim() || null,
      contact_name: form.contact_name?.trim() || null,
      contact_phone: form.contact_phone?.trim() || null,
      contact_email: form.contact_email?.trim() || null,
      memo: form.memo?.trim() || null,
    }
    run(
      () => save.mutateAsync(payload),
      editing ? '매수자 정보가 수정되었습니다.' : '매수자가 등록되었습니다.',
      () => setFormOpen(false),
    )
  }

  const columns: Column<Buyer>[] = [
    {
      key: 'name',
      header: '매수자명',
      render: (b) => (
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-elevate-strong text-sm font-bold text-bone">
            {b.name?.charAt(0) ?? '?'}
          </div>
          <div className="min-w-0">
            <p className="truncate font-semibold text-bone">{b.name}</p>
            <p className="text-xs text-slatey">{b.biz_reg_no ?? '—'}</p>
          </div>
        </div>
      ),
    },
    {
      key: 'type',
      header: '구분',
      render: (b) =>
        b.buyer_type ? (
          <span className="text-xs font-medium text-ash">{buyerTypeLabel(b.buyer_type)}</span>
        ) : (
          <span className="text-xs text-slatey">—</span>
        ),
    },
    {
      key: 'projects',
      header: '참여 사업',
      render: (b) =>
        (b.project_count ?? 0) > 0 ? (
          <span className="font-mono text-sm tabular-nums text-bone">{b.project_count}</span>
        ) : (
          <span
            className="text-xs text-slatey"
            title="아직 어떤 사업에도 연결되지 않았습니다 — 사업 상세의 '거래계약 추가'에서 이 매수자를 선택하면 참여됩니다"
          >
            미참여
          </span>
        ),
    },
    {
      key: 'contact',
      header: '담당자',
      render: (b) => (
        <div>
          <p className="text-sm text-bone">{b.contact_name ?? '—'}</p>
          <p className="text-xs text-slatey">{b.contact_phone ?? b.contact_email ?? ''}</p>
        </div>
      ),
    },
    {
      key: 'created',
      header: '등록일',
      render: (b) => <span className="text-xs text-slatey">{fmtServerDate(b.created_at)}</span>,
    },
    {
      key: 'actions',
      header: '관리',
      className: 'text-right',
      render: (b) => (
        <div className="flex justify-end gap-1">
          <button
            type="button"
            onClick={() => openEdit(b)}
            className="rounded-lg p-1.5 text-smoke hover:bg-elevate hover:text-bone"
            title="수정"
            aria-label={`${b.name} 수정`}
          >
            <PencilSimple size={16} />
          </button>
          <button
            type="button"
            onClick={() => setDeleteTarget(b)}
            className="rounded-lg p-1.5 text-smoke hover:bg-rose-500/10 hover:text-rose-700 dark:hover:text-rose-300"
            title="삭제"
            aria-label={`${b.name} 삭제`}
          >
            <Trash size={16} />
          </button>
        </div>
      ),
    },
  ]

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="매수자 마스터"
        subtitle="탄소배출권 매수자(투자·금융사) 목록 — 부서 공동 관리"
        actions={
          <button
            type="button"
            onClick={openCreate}
            className="flex items-center gap-1.5 rounded-full bg-primary px-3.5 py-2 text-sm font-medium text-on-primary hover:opacity-90"
          >
            <Plus size={16} weight="bold" />
            신규 매수자 등록
          </button>
        }
      />

      {/* 참여 흐름 안내 — 매수자는 '거래계약'으로 사업에 참여한다(등록만으로는 미연결) */}
      <div className="rounded-2xl border border-hairline bg-elevate px-4 py-3 text-xs leading-relaxed text-ash">
        <b className="text-bone">투자사 참여 흐름</b> — ① 여기서 매수자 등록(명부) → ② 감축
        사업 상세의 <b>거래계약 추가</b>에서 이 매수자를 선택(이것이 '참여') → ③ 재무
        원장·세금계산서가 자동 연동 → ④ 필요 시 <b>외부 포털 계정</b>에서 INVESTOR 발급(자기
        매수 사업만 열람). 등록만 하면 '미참여' 상태입니다.
      </div>

      <FilterBar>
        <FilterSearch
          value={search}
          onChange={(v) => {
            setSearch(v)
            setPage(1)
          }}
          placeholder="매수자명·사업자번호 검색"
          className="min-w-[200px] flex-1"
        />
      </FilterBar>

      {isError ? (
        <EmptyState
          icon={<Bank size={36} />}
          title="목록을 불러오지 못했습니다"
          description="네트워크 상태를 확인한 뒤 다시 시도해 주세요."
          action={
            <button
              type="button"
              onClick={() => refetch()}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
            >
              다시 시도
            </button>
          }
        />
      ) : (
        <>
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(b) => b.buyer_id}
            isLoading={isLoading}
            onRowClick={(b) => openEdit(b)}
            emptyTitle="등록된 매수자가 없습니다"
            emptyDescription="우측 상단 [신규 매수자 등록]으로 첫 매수자를 등록할 수 있습니다."
            renderCard={(b) => (
              <div>
                <div className="flex items-center gap-2.5">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-elevate-strong text-sm font-bold text-bone">
                    {b.name?.charAt(0) ?? '?'}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold text-bone">{b.name}</p>
                    <p className="text-xs text-slatey">
                      {b.buyer_type ? buyerTypeLabel(b.buyer_type) : '—'} ·{' '}
                      {b.contact_name ?? '담당자 미지정'}
                    </p>
                  </div>
                </div>
              </div>
            )}
          />
          {total > 0 && (
            <Pagination total={total} page={page} pageSize={PAGE_SIZE} onChange={setPage} />
          )}
        </>
      )}

      {/* 등록·수정 모달 */}
      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title={editing ? '매수자 정보 수정' : '신규 매수자 등록'}
        footer={
          <>
            <button
              type="button"
              onClick={() => setFormOpen(false)}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
            >
              취소
            </button>
            <button
              type="button"
              disabled={!form.name.trim() || save.isPending}
              onClick={submit}
              className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
            >
              {editing ? '저장' : '등록'}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-ash">
              매수자명<span className="ml-0.5 text-rose-500">*</span>
            </label>
            <input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="예: 후시증권"
              className={inputCls}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-ash">구분</label>
              <select
                value={form.buyer_type ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, buyer_type: e.target.value }))}
                className={inputCls}
              >
                <option value="">선택 안 함</option>
                {buyerTypeOptions.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-ash">사업자번호</label>
              <input
                value={form.biz_reg_no ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, biz_reg_no: e.target.value }))}
                placeholder="000-00-00000"
                className={inputCls}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-ash">담당자명</label>
              <input
                value={form.contact_name ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, contact_name: e.target.value }))}
                className={inputCls}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-ash">담당자 연락처</label>
              <input
                value={form.contact_phone ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, contact_phone: e.target.value }))}
                className={inputCls}
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ash">담당자 이메일</label>
            <input
              type="email"
              value={form.contact_email ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, contact_email: e.target.value }))}
              placeholder="name@example.com"
              className={inputCls}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ash">메모</label>
            <textarea
              value={form.memo ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, memo: e.target.value }))}
              rows={2}
              className="w-full rounded-lg border border-hairline bg-graphite px-3 py-2 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
            />
          </div>
        </div>
      </Modal>

      {/* 삭제 확인 */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="매수자 삭제"
        message={
          <>
            <b>{deleteTarget?.name}</b> 매수자를 삭제합니다. 되돌릴 수 없습니다.
          </>
        }
        confirmLabel="삭제"
        danger
        loading={remove.isPending}
        onConfirm={() =>
          deleteTarget &&
          run(
            () => remove.mutateAsync(deleteTarget.buyer_id),
            '매수자가 삭제되었습니다.',
            () => setDeleteTarget(null),
          )
        }
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
