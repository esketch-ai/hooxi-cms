// SCR-03 고객사 마스터 목록 — 기본 필터 '전체 고객사' (공동 관리)
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Buildings, PencilSimple, Phone, Plus } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { FilterBar, FilterSearch, FilterSelect } from '../../components/FilterBar'
import { DataTable, type Column } from '../../components/DataTable'
import { Pagination } from '../../components/Pagination'
import { StatusBadge } from '../../components/StatusBadge'
import { SensitiveData } from '../../components/SensitiveData'
import { EmptyState } from '../../components/EmptyState'
import { useUserOptions } from '../../lib/api/queries'
import { fmtDate, telHref } from '../../lib/format'
import type { Client } from '../../types'
import { useClients } from './api'
import { ClientFormModal } from './ClientFormModal'

const PAGE_SIZE = 20

/** 고객사명 이니셜 아바타 */
export function ClientAvatar({ name, className = '' }: { name?: string | null; className?: string }) {
  return (
    <div
      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-elevate-strong text-sm font-bold text-bone ${className}`}
    >
      {name?.charAt(0) ?? '?'}
    </div>
  )
}

export function ClientsPage() {
  const navigate = useNavigate()
  const { data: users = [] } = useUserOptions()

  const [clientType, setClientType] = useState('')
  const [contractStatus, setContractStatus] = useState('')
  const [managerId, setManagerId] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Client | null>(null)

  const filters = useMemo(
    () => ({
      client_type: clientType,
      contract_status: contractStatus,
      manager_id: managerId,
      search,
      page,
      page_size: PAGE_SIZE,
    }),
    [clientType, contractStatus, managerId, search, page],
  )

  const { data, isLoading, isError, refetch } = useClients(filters)
  const rows = data?.items ?? []
  const total = data?.total ?? 0

  const openEdit = (client: Client) => {
    setEditing(client)
    setFormOpen(true)
  }

  const columns: Column<Client>[] = [
    {
      key: 'name',
      header: '고객사명',
      render: (c) => (
        <div className="flex items-center gap-2.5">
          <ClientAvatar name={c.company_name} />
          <div className="min-w-0">
            <Link
              to={`/clients/${c.client_id}`}
              className="block truncate font-semibold text-bone hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              {c.company_name}
            </Link>
            <p className="text-xs text-slatey">{c.biz_reg_no ?? '—'}</p>
          </div>
        </div>
      ),
    },
    {
      key: 'type',
      header: '구분',
      render: (c) => (
        <span className="text-xs font-medium text-ash">
          {c.client_type === 'TRANSPORT' ? '운수사' : '건물·농장'}
        </span>
      ),
    },
    {
      key: 'contact',
      header: '주 담당자',
      render: (c) => (
        <div>
          <p className="text-sm text-bone">{c.main_contact_name ?? '—'}</p>
          <p className="text-xs text-slatey">{c.main_contact_phone ?? ''}</p>
        </div>
      ),
    },
    {
      key: 'fee',
      header: '성공 보수율',
      render: (c) =>
        c.success_fee_rate != null ? (
          <SensitiveData type="rate" value={`${c.success_fee_rate} %`} />
        ) : (
          <span className="text-slatey">—</span>
        ),
    },
    {
      key: 'lastActivity',
      header: '최근 활동',
      render: (c) => (
        <span className="text-xs text-ash">{fmtDate(c.last_activity_at)}</span>
      ),
    },
    {
      key: 'report',
      header: '이번 달 보고서',
      render: (c) =>
        c.report_status_this_month ? (
          <StatusBadge domain="report" value={c.report_status_this_month} />
        ) : (
          <span className="text-xs text-slatey">대상 아님</span>
        ),
    },
    {
      key: 'status',
      header: '계약 상태',
      render: (c) => <StatusBadge domain="contract" value={c.contract_status} />,
    },
    {
      key: 'actions',
      header: '관리',
      className: 'text-right',
      render: (c) => (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            openEdit(c)
          }}
          className="rounded-lg p-1.5 text-smoke hover:bg-elevate hover:text-bone"
          title="수정"
          aria-label={`${c.company_name} 수정`}
        >
          <PencilSimple size={16} />
        </button>
      ),
    },
  ]

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="고객사 마스터"
        subtitle="전체 고객사 목록 — 부서 공동 관리"
        actions={
          /* 신규 등록 — 모바일 숨김 (§7.1) */
          <button
            type="button"
            onClick={() => {
              setEditing(null)
              setFormOpen(true)
            }}
            className="hidden items-center gap-1.5 rounded-full bg-primary px-3.5 py-2 text-sm font-medium text-on-primary hover:opacity-90 sm:flex"
          >
            <Plus size={16} weight="bold" />
            신규 고객사 등록
          </button>
        }
      />

      <FilterBar>
        <FilterSelect
          label="구분"
          value={clientType}
          onChange={(v) => {
            setClientType(v)
            setPage(1)
          }}
          options={[
            { value: 'TRANSPORT', label: '운수사' },
            { value: 'FACILITY', label: '건물·농장' },
          ]}
        />
        <FilterSelect
          label="계약 상태"
          value={contractStatus}
          onChange={(v) => {
            setContractStatus(v)
            setPage(1)
          }}
          options={[
            { value: 'ACTIVE', label: '계약중' },
            { value: 'HOLD', label: '보류' },
            { value: 'END', label: '종료' },
          ]}
        />
        <FilterSelect
          label="담당 PM"
          value={managerId}
          onChange={(v) => {
            setManagerId(v)
            setPage(1)
          }}
          options={users.map((u) => ({ value: u.user_id, label: u.name }))}
        />
        <FilterSearch
          value={search}
          onChange={(v) => {
            setSearch(v)
            setPage(1)
          }}
          placeholder="고객사명·사업자번호 검색"
          className="min-w-[200px] flex-1"
        />
      </FilterBar>

      {isError ? (
        <EmptyState
          icon={<Buildings size={36} />}
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
            rowKey={(c) => c.client_id}
            isLoading={isLoading}
            onRowClick={(c) => navigate(`/clients/${c.client_id}`)}
            /* HOLD 행 톤 다운 */
            rowClassName={(c) => (c.contract_status === 'HOLD' ? 'opacity-55' : '')}
            emptyTitle="등록된 고객사가 없습니다"
            emptyDescription="우측 상단 [신규 고객사 등록]으로 첫 고객사를 등록해 보세요."
            renderCard={(c) => (
              /* 모바일 카드 — Click-to-Call (§7) */
              <div>
                <div className="flex items-center gap-2.5">
                  <ClientAvatar name={c.company_name} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold text-bone">{c.company_name}</p>
                    <p className="text-xs text-slatey">
                      {c.client_type === 'TRANSPORT' ? '운수사' : '건물·농장'} ·{' '}
                      {c.main_contact_name ?? '—'}
                    </p>
                  </div>
                  <StatusBadge domain="contract" value={c.contract_status} />
                </div>
                <div className="mt-3 flex gap-2">
                  {c.main_contact_phone && (
                    <a
                      href={telHref(c.main_contact_phone)}
                      className="flex flex-1 items-center justify-center gap-1.5 rounded-full bg-primary py-2 text-sm font-medium text-on-primary"
                    >
                      <Phone size={15} weight="fill" />
                      전화
                    </a>
                  )}
                  <Link
                    to={`/clients/${c.client_id}`}
                    className="flex flex-1 items-center justify-center rounded-full border border-hairline py-2 text-sm font-medium text-bone"
                  >
                    상세 보기
                  </Link>
                </div>
              </div>
            )}
          />
          {total > 0 && (
            <Pagination total={total} page={page} pageSize={PAGE_SIZE} onChange={setPage} />
          )}
        </>
      )}

      <ClientFormModal open={formOpen} onClose={() => setFormOpen(false)} client={editing} />
    </div>
  )
}
