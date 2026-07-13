// SCR-04 자산 및 연동 현황 — 외부기관 연동 계정의 안전한 공동 관리
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowSquareOut, CircleNotch, HardDrives, PencilSimple, Plus } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { FilterBar, FilterSearch, FilterSelect } from '../../components/FilterBar'
import { DataTable, type Column } from '../../components/DataTable'
import { Pagination } from '../../components/Pagination'
import { StatusBadge } from '../../components/StatusBadge'
import { EmptyState } from '../../components/EmptyState'
import { useCodes } from '../../lib/api/queries'
import type { Asset } from '../../types'
import { useAssets } from './api'
import { useRevealAuth } from './useRevealAuth'
import { AssetFormModal } from './AssetFormModal'

const PAGE_SIZE = 20

/** 자산 분류·제원 셀 — 연료 배지 + 수량 + 관제 Y/N (§3.3) */
function AssetSpecCell({ asset }: { asset: Asset }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {asset.asset_type && <StatusBadge domain="assetType" value={asset.asset_type} />}
      <span className="text-sm text-bone">
        {asset.main_spec ?? (asset.asset_group === 'MOBILITY' ? '차량' : '설비')}
        {asset.quantity != null && (
          <span className="ml-1 font-semibold text-bone">{asset.quantity}대</span>
        )}
      </span>
      <span
        className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold ${
          asset.telemetry_yn === 'Y'
            ? 'border-emerald-400/25 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
            : 'border-hairline bg-elevate-strong text-ash'
        }`}
      >
        관제 {asset.telemetry_yn === 'Y' ? 'Y' : 'N'}
      </span>
    </div>
  )
}

const AUTH_TYPE_LABEL: Record<string, string> = {
  API_KEY: 'API 키',
  ID_PW: 'ID/PW',
  NONE: '없음',
}

/** 보안 접속 정보 셀 — 마스킹 클릭 → 서버 reveal → 자동 재마스킹 (SCR-04 §5) */
function AuthCell({
  asset,
  revealed,
  loading,
  onReveal,
  onHide,
}: {
  asset: Asset
  revealed: string | null
  loading: boolean
  onReveal: () => void
  onHide: () => void
}) {
  if (!asset.auth_type || asset.auth_type === 'NONE') {
    return <span className="text-xs text-slatey">—</span>
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="inline-flex items-center rounded border border-hairline bg-elevate-strong px-1.5 py-0.5 font-mono text-[10px] font-semibold text-ash">
        {AUTH_TYPE_LABEL[asset.auth_type] ?? asset.auth_type}
      </span>
      {/* login_id는 평문 (SCR-04 §7) */}
      {asset.auth_type === 'ID_PW' && asset.login_id && (
        <span className="font-mono text-xs text-ash">{asset.login_id}</span>
      )}
      {!asset.has_credentials ? (
        <span className="text-xs text-slatey">미설정</span>
      ) : revealed != null ? (
        <button
          type="button"
          onClick={onHide}
          className="max-w-[180px] cursor-pointer truncate rounded bg-amber-500/15 px-1.5 py-0.5 font-mono text-xs text-amber-800 dark:text-amber-100"
          title="잠시 후 자동으로 다시 가려집니다 — 클릭 시 즉시 숨김"
        >
          {revealed}
        </button>
      ) : (
        <button
          type="button"
          onClick={onReveal}
          disabled={loading}
          className="flex items-center gap-1 rounded bg-elevate-strong px-1.5 py-0.5 font-mono text-xs tracking-tight text-smoke select-none hover:bg-white/15 disabled:opacity-60"
          title="클릭하여 일시 표시 (감사 로그 기록)"
          aria-label="보안 접속 정보 — 클릭하여 일시 표시"
        >
          {loading ? <CircleNotch size={12} className="animate-spin" /> : '••••••••'}
        </button>
      )}
      {asset.site_url && (
        <a
          href={asset.site_url}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="text-ash hover:text-bone"
          title={asset.site_url}
          aria-label="연동 사이트 열기"
        >
          <ArrowSquareOut size={14} />
        </a>
      )}
    </div>
  )
}

export function AssetsPage() {
  const { options: assetGroupOptions } = useCodes('ASSET_GROUP')
  const [assetGroup, setAssetGroup] = useState('')
  const [telemetryYn, setTelemetryYn] = useState('')
  const [authType, setAuthType] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Asset | null>(null)

  const filters = useMemo(
    () => ({
      asset_category: assetGroup,
      monitoring_yn: telemetryYn,
      auth_method: authType,
      search,
      page,
      page_size: PAGE_SIZE,
    }),
    [assetGroup, telemetryYn, authType, search, page],
  )

  const { data, isLoading, isError, refetch } = useAssets(filters)
  const rows = data?.items ?? []
  const total = data?.total ?? 0

  const { revealed, loadingId, reveal, hide } = useRevealAuth()

  const openEdit = (asset: Asset) => {
    setEditing(asset)
    setFormOpen(true)
  }

  const authCell = (a: Asset) => (
    <AuthCell
      asset={a}
      revealed={revealed?.assetId === a.asset_id ? revealed.value : null}
      loading={loadingId === a.asset_id}
      onReveal={() => reveal(a.asset_id)}
      onHide={hide}
    />
  )

  const columns: Column<Asset>[] = [
    {
      key: 'client',
      header: '고객사',
      render: (a) => (
        <Link
          to={`/clients/${a.client_id}`}
          onClick={(e) => e.stopPropagation()}
          className="font-semibold text-bone hover:underline"
        >
          {a.client_name ?? '—'}
        </Link>
      ),
    },
    {
      key: 'spec',
      header: '자산 분류·제원',
      render: (a) => <AssetSpecCell asset={a} />,
    },
    {
      key: 'agency',
      header: '대상 기관',
      render: (a) =>
        a.agency_name ? (
          <div>
            <p className="text-sm text-bone">{a.agency_name}</p>
            {a.usage_purpose && <p className="text-xs text-slatey">{a.usage_purpose}</p>}
          </div>
        ) : (
          <span className="text-xs text-slatey">기관 미설정</span>
        ),
    },
    {
      key: 'auth',
      header: '보안 접속 정보',
      render: authCell,
    },
    {
      key: 'status',
      header: '상태',
      render: (a) => (a.status ? <StatusBadge domain="assetStatus" value={a.status} /> : null),
    },
    {
      key: 'actions',
      header: '수정',
      className: 'text-right',
      render: (a) => (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            openEdit(a)
          }}
          className="rounded-lg p-1.5 text-smoke hover:bg-elevate hover:text-bone"
          title="수정"
          aria-label="자산 수정"
        >
          <PencilSimple size={16} />
        </button>
      ),
    },
  ]

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="자산 및 연동 현황"
        subtitle="고객사 자산·관제 연동·외부기관 접속 계정 공동 관리"
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
            신규 자산 등록
          </button>
        }
      />

      <FilterBar>
        <FilterSelect
          label="대분류"
          value={assetGroup}
          onChange={(v) => {
            setAssetGroup(v)
            setPage(1)
          }}
          options={assetGroupOptions}
        />
        <FilterSelect
          label="관제 연동"
          value={telemetryYn}
          onChange={(v) => {
            setTelemetryYn(v)
            setPage(1)
          }}
          options={[
            { value: 'Y', label: '연동 (Y)' },
            { value: 'N', label: '미연동 (N)' },
          ]}
        />
        <FilterSelect
          label="인증 방식"
          value={authType}
          onChange={(v) => {
            setAuthType(v)
            setPage(1)
          }}
          options={[
            { value: 'API_KEY', label: 'API 키' },
            { value: 'ID_PW', label: 'ID/PW' },
            { value: 'NONE', label: '없음' },
          ]}
        />
        <FilterSearch
          value={search}
          onChange={(v) => {
            setSearch(v)
            setPage(1)
          }}
          placeholder="고객사 검색"
          className="min-w-[200px] flex-1"
        />
      </FilterBar>

      {isError ? (
        <EmptyState
          icon={<HardDrives size={36} />}
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
            rowKey={(a) => a.asset_id}
            isLoading={isLoading}
            emptyTitle="등록된 자산이 없습니다"
            emptyDescription="우측 상단 [신규 자산 등록]으로 첫 자산을 등록해 보세요."
            renderCard={(a) => (
              /* 모바일 카드 — 열람 위주, reveal 3초 (§7) */
              <div className="space-y-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <Link
                      to={`/clients/${a.client_id}`}
                      className="truncate font-semibold text-bone"
                    >
                      {a.client_name ?? '—'}
                    </Link>
                    <p className="mt-0.5 text-xs text-slatey">
                      {a.agency_name ?? '기관 미설정'}
                    </p>
                  </div>
                  {a.status && <StatusBadge domain="assetStatus" value={a.status} />}
                </div>
                <AssetSpecCell asset={a} />
                <div className="border-t border-hairline pt-2">{authCell(a)}</div>
              </div>
            )}
          />
          {total > 0 && (
            <Pagination total={total} page={page} pageSize={PAGE_SIZE} onChange={setPage} />
          )}
        </>
      )}

      <AssetFormModal open={formOpen} onClose={() => setFormOpen(false)} asset={editing} />
    </div>
  )
}
