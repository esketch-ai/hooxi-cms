// 수집 계정 관리 — 고객이 제공한 외부 사이트(ETAS·BMS·태양광·히트펌프 등) 로그인 계정 통합 뷰.
// 자산(SCR-04)의 계정 필드를 "계정 중심"으로 재구성. 등록/수정 폼·reveal 훅은 assets 재사용.
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowSquareOut,
  CircleNotch,
  KeyReturn,
  LockKey,
  PencilSimple,
  Plus,
  ShieldCheck,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { FilterBar, FilterSearch, FilterSelect } from '../../components/FilterBar'
import { DataTable, type Column } from '../../components/DataTable'
import { Pagination } from '../../components/Pagination'
import { StatusBadge } from '../../components/StatusBadge'
import { EmptyState } from '../../components/EmptyState'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import type { AccountCheckResponse, Asset } from '../../types'
import { useRevealAuth } from '../assets/useRevealAuth'
import { AssetFormModal } from '../assets/AssetFormModal'
import { useAccountCheck, useCredentialAssets } from './api'

const PAGE_SIZE = 20

const AUTH_TYPE_LABEL: Record<string, string> = {
  API_KEY: 'API 키',
  ID_PW: 'ID/PW',
}

/** 인증 방식 배지 */
function AuthMethodBadge({ authType }: { authType?: string | null }) {
  if (!authType || authType === 'NONE') return <span className="text-xs text-slatey">—</span>
  return (
    <span className="inline-flex items-center rounded border border-hairline bg-elevate-strong px-1.5 py-0.5 font-mono text-[10px] font-semibold text-ash">
      {AUTH_TYPE_LABEL[authType] ?? authType}
    </span>
  )
}

/** 비밀번호/키 셀 — 마스킹 클릭 → 서버 reveal(평문 일시 표시) → 자동 재마스킹 (§5) */
function SecretCell({
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
  if (!asset.has_credentials) {
    return <span className="text-xs text-slatey">미설정</span>
  }
  if (revealed != null) {
    return (
      <button
        type="button"
        onClick={onHide}
        className="max-w-[200px] cursor-pointer truncate rounded bg-amber-500/15 px-1.5 py-0.5 font-mono text-xs text-amber-800 dark:text-amber-100"
        title="잠시 후 자동으로 다시 가려집니다 — 클릭 시 즉시 숨김"
      >
        {revealed}
      </button>
    )
  }
  return (
    <button
      type="button"
      onClick={onReveal}
      disabled={loading}
      className="flex items-center gap-1 rounded bg-elevate-strong px-1.5 py-0.5 font-mono text-xs tracking-tight text-smoke select-none hover:bg-white/15 disabled:opacity-60"
      title="클릭하여 일시 표시 (감사 로그 기록)"
      aria-label="비밀번호/키 — 클릭하여 일시 표시"
    >
      {loading ? <CircleNotch size={12} className="animate-spin" /> : '••••••••'}
    </button>
  )
}

export function AccountsPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'ADMIN'
  const { showToast } = useToast()

  const [assetGroup, setAssetGroup] = useState('')
  const [authType, setAuthType] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Asset | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [lastResult, setLastResult] = useState<AccountCheckResponse | null>(null)

  const filters = useMemo(
    () => ({
      asset_category: assetGroup,
      auth_method: authType,
      search,
      page,
      page_size: PAGE_SIZE,
    }),
    [assetGroup, authType, search, page],
  )

  const { data, isLoading, isError, refetch } = useCredentialAssets(filters)
  const rows = data?.items ?? []
  const total = data?.total ?? 0

  const { revealed, loadingId, reveal, hide } = useRevealAuth()
  const accountCheck = useAccountCheck()

  const openEdit = (asset: Asset) => {
    setEditing(asset)
    setFormOpen(true)
  }

  const closeForm = () => {
    setFormOpen(false)
    // 등록/수정 후 계정 목록 최신화 (useSaveAsset은 'assets' 키만 무효화)
    refetch()
  }

  const runAccountCheck = async () => {
    try {
      const res = await accountCheck.mutateAsync()
      setConfirmOpen(false)
      setLastResult(res)
      showToast(
        `계정 점검 완료 — 대상 ${res.targets} · 생성 ${res.created} · 사이트장애 ${res.unreachable}`,
        res.unreachable > 0 ? 'info' : 'success',
      )
    } catch {
      showToast('점검 실행에 실패했습니다. 권한 또는 네트워크를 확인해 주세요.', 'danger')
    }
  }

  const secretCell = (a: Asset) => (
    <SecretCell
      asset={a}
      revealed={revealed?.assetId === a.asset_id ? revealed.value : null}
      loading={loadingId === a.asset_id}
      onReveal={() => reveal(a.asset_id)}
      onHide={hide}
    />
  )

  const siteLink = (a: Asset) =>
    a.site_url ? (
      <a
        href={a.site_url}
        target="_blank"
        rel="noreferrer"
        onClick={(e) => e.stopPropagation()}
        className="inline-flex items-center gap-1 text-sm text-ash hover:text-bone hover:underline"
        title={a.site_url}
      >
        <span className="max-w-[180px] truncate">{a.site_url.replace(/^https?:\/\//, '')}</span>
        <ArrowSquareOut size={13} className="shrink-0" />
      </a>
    ) : (
      <span className="text-xs text-slatey">—</span>
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
      key: 'agency',
      header: '대상 기관',
      render: (a) =>
        a.agency_name ? (
          <span className="text-sm text-bone">{a.agency_name}</span>
        ) : (
          <span className="text-xs text-slatey">기관 미설정</span>
        ),
    },
    { key: 'site', header: '사이트', render: siteLink },
    { key: 'auth', header: '인증 방식', render: (a) => <AuthMethodBadge authType={a.auth_type} /> },
    {
      key: 'login',
      header: '로그인 ID',
      render: (a) =>
        a.auth_type === 'ID_PW' && a.login_id ? (
          <span className="font-mono text-xs text-ash">{a.login_id}</span>
        ) : (
          <span className="text-xs text-slatey">—</span>
        ),
    },
    { key: 'secret', header: '비밀번호/키', render: secretCell },
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
          aria-label="계정 수정"
        >
          <PencilSimple size={16} />
        </button>
      ),
    },
  ]

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="수집 계정 관리"
        subtitle="고객이 제공한 외부 사이트 로그인 계정 통합 관리"
        actions={
          <div className="hidden items-center gap-2 sm:flex">
            {isAdmin && (
              <button
                type="button"
                onClick={() => setConfirmOpen(true)}
                className="flex items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-semibold text-bone hover:bg-elevate"
              >
                <ShieldCheck size={16} weight="bold" />
                지금 전체 점검
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                setEditing(null)
                setFormOpen(true)
              }}
              className="flex items-center gap-1.5 rounded-full bg-primary px-3.5 py-2 text-sm font-medium text-on-primary hover:opacity-90"
            >
              <Plus size={16} weight="bold" />
              계정 등록
            </button>
          </div>
        }
      />

      {/* 안내 배너 */}
      <div className="flex items-start gap-2.5 rounded-2xl border border-hairline bg-graphite px-4 py-3">
        <KeyReturn size={18} className="mt-0.5 shrink-0 text-slatey" />
        <p className="text-sm leading-relaxed text-ash">
          고객이 제공한 로그인 계정을 관리합니다. 매월 1일 자동 점검 이슈가 생성되며,
          <span className="font-semibold text-bone"> [지금 전체 점검]</span>으로 즉시 생성할 수
          있습니다.
        </p>
      </div>

      {/* 점검 실행 결과 — 이슈 보드 링크 (토스트는 자동 소멸하므로 결과는 배너로 유지) */}
      {lastResult && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-emerald-400/25 bg-emerald-500/15 px-4 py-3">
          <p className="text-sm text-emerald-700 dark:text-emerald-300">
            <span className="font-semibold">계정 점검 완료</span> — 대상 {lastResult.targets} · 생성{' '}
            {lastResult.created} · 건너뜀 {lastResult.skipped} · 사이트장애 {lastResult.unreachable}
          </p>
          <div className="flex items-center gap-3">
            <Link to="/issues" className="text-sm font-semibold text-emerald-700 dark:text-emerald-300 hover:underline">
              이슈 보드에서 보기 →
            </Link>
            <button
              type="button"
              onClick={() => setLastResult(null)}
              className="text-sm text-emerald-700 hover:text-emerald-800 dark:text-emerald-300"
              aria-label="결과 닫기"
            >
              닫기
            </button>
          </div>
        </div>
      )}

      <FilterBar>
        <FilterSelect
          label="대분류"
          value={assetGroup}
          onChange={(v) => {
            setAssetGroup(v)
            setPage(1)
          }}
          options={[
            { value: 'MOBILITY', label: '모빌리티' },
            { value: 'FACILITY', label: '설비' },
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
            { value: 'ID_PW', label: 'ID/PW' },
            { value: 'API_KEY', label: 'API 키' },
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
          icon={<LockKey size={36} />}
          title="계정 목록을 불러오지 못했습니다"
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
            emptyTitle="등록된 수집 계정이 없습니다"
            emptyDescription="우측 상단 [계정 등록]으로 첫 로그인 계정을 등록해 보세요."
            renderCard={(a) => (
              <div className="space-y-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <Link
                      to={`/clients/${a.client_id}`}
                      className="truncate font-semibold text-bone"
                    >
                      {a.client_name ?? '—'}
                    </Link>
                    <p className="mt-0.5 text-xs text-slatey">{a.agency_name ?? '기관 미설정'}</p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {a.status && <StatusBadge domain="assetStatus" value={a.status} />}
                    <button
                      type="button"
                      onClick={() => openEdit(a)}
                      className="rounded-lg p-1 text-smoke hover:bg-elevate hover:text-bone"
                      aria-label="계정 수정"
                    >
                      <PencilSimple size={15} />
                    </button>
                  </div>
                </div>
                <div className="flex items-center justify-between gap-2 border-t border-hairline pt-2">
                  {siteLink(a)}
                  <AuthMethodBadge authType={a.auth_type} />
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {a.auth_type === 'ID_PW' && a.login_id && (
                    <span className="font-mono text-xs text-ash">{a.login_id}</span>
                  )}
                  {secretCell(a)}
                </div>
              </div>
            )}
          />
          {total > 0 && (
            <Pagination total={total} page={page} pageSize={PAGE_SIZE} onChange={setPage} />
          )}
        </>
      )}

      <AssetFormModal open={formOpen} onClose={closeForm} asset={editing} />

      <ConfirmDialog
        open={confirmOpen}
        title="전체 계정 점검 실행"
        message={
          <>
            전체 계정의 월별 점검 이슈를 생성합니다. 이미 이번 달 이슈가 있는 계정은 건너뜁니다.
            <br />
            계속하시겠습니까?
          </>
        }
        confirmLabel="점검 실행"
        loading={accountCheck.isPending}
        onConfirm={runAccountCheck}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  )
}
