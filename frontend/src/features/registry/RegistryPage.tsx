// 감축 참여 레지스트리(KISA 500대) — 참여 상태별 차량 현황 원장(M3).
// BASELINE(대체 전 화석연료)·PROJECT(전기버스 참여)·CANDIDATE(대체예정 미참여) + 업로드.
import { useMemo, useState } from 'react'
import { CircleNotch, UploadSimple } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import { useImportRegistry, useRegistry, useRegistrySummary } from './api'

const ROLE_META: Record<string, { label: string; cls: string }> = {
  BASELINE: { label: '베이스라인(화석연료)', cls: 'bg-slate-500/15 text-slate-700 dark:text-slate-300 border-slate-400/25' },
  PROJECT: { label: '전기버스(참여)', cls: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-400/25' },
  CANDIDATE: { label: '대체예정(미참여)', cls: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-400/25' },
}

function RoleBadge({ role }: { role: string }) {
  const m = ROLE_META[role] ?? { label: role, cls: 'bg-elevate-strong text-ash border-hairline' }
  return <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${m.cls}`}>{m.label}</span>
}

export function RegistryPage() {
  const { showToast } = useToast()
  const { user } = useAuth()
  const canWrite = !!user && ['ADMIN', 'MANAGER', 'STAFF'].includes(user.role)
  const { data: summary } = useRegistrySummary()
  const [role, setRole] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 50
  const { data, isLoading } = useRegistry({ role: role || undefined, search: search.trim() || undefined, page, page_size: pageSize })
  const importM = useImportRegistry()

  const onUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    try {
      const r = await importM.mutateAsync(files[0])
      showToast(`적재 완료 — 총 ${r.created}건(참여 ${r.project}·베이스라인 ${r.baseline}·대체예정 ${r.candidate}) · 운수사매칭 ${r.client_matched}`, 'success')
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '적재에 실패했습니다.', 'danger')
    }
  }

  const total = data?.total ?? 0
  const maxPage = Math.max(1, Math.ceil(total / pageSize))
  const matchRate = useMemo(
    () => (summary && summary.total > 0 ? Math.round((summary.client_matched / summary.total) * 100) : 0),
    [summary],
  )

  const TILES = [
    { key: '', label: '전체', value: summary?.total ?? 0 },
    { key: 'PROJECT', label: '전기버스(참여)', value: summary?.project ?? 0 },
    { key: 'BASELINE', label: '베이스라인', value: summary?.baseline ?? 0 },
    { key: 'CANDIDATE', label: '대체예정(미참여)', value: summary?.candidate ?? 0 },
  ]

  return (
    <div className="space-y-5">
      <PageHeader title="감축 참여 레지스트리" subtitle="프로그램 전체 차량 현황(KISA) — 참여·베이스라인·대체예정" />

      {/* 요약 타일 — 클릭 시 role 필터 */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {TILES.map((t) => (
          <button
            key={t.label}
            type="button"
            onClick={() => { setRole(t.key); setPage(1) }}
            className={`rounded-2xl border p-4 text-left transition-colors ${
              role === t.key ? 'border-primary/60 bg-elevate-strong' : 'border-hairline bg-graphite hover:bg-elevate'
            }`}
          >
            <p className="text-[11px] font-medium uppercase tracking-wider text-slatey">{t.label}</p>
            <p className="mt-1 text-2xl font-bold tabular-nums text-bone">{t.value.toLocaleString('ko-KR')}</p>
          </button>
        ))}
      </div>
      <p className="text-xs text-slatey">운수사 매칭률 {matchRate}% ({summary?.client_matched ?? 0}/{summary?.total ?? 0}) · 대체예정은 아직 사업에 안 들어간 향후 참여 대상입니다.</p>

      {/* 툴바 */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          placeholder="차량번호·업체명·차명 검색"
          className="h-9 w-56 rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
        />
        {canWrite && (
          <label className="ml-auto flex cursor-pointer items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate">
            {importM.isPending ? <CircleNotch size={15} className="animate-spin" /> : <UploadSimple size={15} />}
            KISA 엑셀 적재
            <input type="file" accept=".xlsx" className="hidden" onChange={(e) => onUpload(e.target.files)} />
          </label>
        )}
      </div>

      {/* 목록 */}
      <section className="rounded-2xl border border-hairline bg-graphite p-5">
        <p className="mb-3 text-sm font-semibold text-bone">차량 목록 ({total.toLocaleString('ko-KR')})</p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="border-b border-hairline text-[11px] uppercase tracking-wider text-slatey">
              <tr>
                <th className="px-2 py-2">상태</th>
                <th className="px-2 py-2">차량번호</th>
                <th className="px-2 py-2">운수사</th>
                <th className="px-2 py-2">도입구분</th>
                <th className="px-2 py-2">차명</th>
                <th className="px-2 py-2">연식</th>
                <th className="px-2 py-2 text-right">정원</th>
                <th className="px-2 py-2">연료</th>
                <th className="px-2 py-2">권역</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && !data ? (
                <tr><td colSpan={9} className="px-2 py-8 text-center text-ash"><CircleNotch size={16} className="mx-auto animate-spin" /></td></tr>
              ) : (data?.items ?? []).length === 0 ? (
                <tr><td colSpan={9} className="px-2 py-8 text-center text-slatey">데이터가 없습니다. {canWrite ? 'KISA 엑셀을 적재하세요.' : ''}</td></tr>
              ) : (
                (data?.items ?? []).map((r) => (
                  <tr key={r.registry_id} className="border-b border-hairline/60">
                    <td className="px-2 py-2"><RoleBadge role={r.role} /></td>
                    <td className="px-2 py-2 font-medium text-bone">{r.vehicle_no}</td>
                    <td className="px-2 py-2 text-ash">{r.client_name ?? r.operator_name ?? '—'}</td>
                    <td className="px-2 py-2 text-ash">{r.introduction_type ?? '—'}</td>
                    <td className="px-2 py-2 text-ash">{r.model_name ?? '—'}</td>
                    <td className="px-2 py-2 text-ash">{r.model_year ?? '—'}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-ash">{r.seating_capacity ?? '—'}</td>
                    <td className="px-2 py-2 text-ash">{r.fuel ?? '—'}</td>
                    <td className="px-2 py-2 text-ash">{r.region ?? '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {maxPage > 1 && (
          <div className="mt-3 flex items-center justify-end gap-2 text-sm">
            <button type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))} className="rounded-lg border border-hairline px-3 py-1.5 text-bone hover:bg-elevate disabled:opacity-40">이전</button>
            <span className="text-ash">{page} / {maxPage}</span>
            <button type="button" disabled={page >= maxPage} onClick={() => setPage((p) => Math.min(maxPage, p + 1))} className="rounded-lg border border-hairline px-3 py-1.5 text-bone hover:bg-elevate disabled:opacity-40">다음</button>
          </div>
        )}
      </section>
    </div>
  )
}
