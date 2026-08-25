// 충전 인프라(차고지·충전기·AC전력량계) — MRV 증빙(D3).
import { useState } from 'react'
import { CircleNotch, UploadSimple } from '@phosphor-icons/react'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import { useChargingSummary, useFacilities, useImportCharging } from './chargingApi'

export function ChargingInfraPanel() {
  const { showToast } = useToast()
  const { user } = useAuth()
  const canWrite = !!user && ['ADMIN', 'MANAGER', 'STAFF'].includes(user.role)
  const { data: summary } = useChargingSummary()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 50
  const { data, isLoading } = useFacilities({ search: search.trim() || undefined, page, page_size: pageSize })
  const importM = useImportCharging()

  const onUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    try {
      const r = await importM.mutateAsync(files[0])
      showToast(`적재 완료 — 차고지 ${r.facilities}·충전기 ${r.chargers}·전력량계 ${r.meters}`, 'success')
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '적재에 실패했습니다.', 'danger')
    }
  }
  const total = data?.total ?? 0
  const maxPage = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Tile label="차고지" value={summary?.facilities ?? 0} />
        <Tile label="충전기" value={summary?.chargers ?? 0} />
        <Tile label="AC전력량계" value={summary?.meters ?? 0} />
      </div>
      <p className="text-xs text-slatey">지역별 충전기 제원 엑셀을 올리면 해당 권역만 교체 적재됩니다. MRV(측정·검증) 증빙.</p>

      <div className="flex flex-wrap items-center gap-2">
        <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} placeholder="운수사·주소 검색"
          className="h-9 w-56 rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none" />
        {canWrite && (
          <label className="ml-auto flex cursor-pointer items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate">
            {importM.isPending ? <CircleNotch size={15} className="animate-spin" /> : <UploadSimple size={15} />}
            충전기 제원 엑셀 적재
            <input type="file" accept=".xlsx" className="hidden" onChange={(e) => onUpload(e.target.files)} />
          </label>
        )}
      </div>

      <section className="rounded-2xl border border-hairline bg-graphite p-5">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="border-b border-hairline text-[11px] uppercase tracking-wider text-slatey">
              <tr>
                <th className="px-2 py-2">운수사</th>
                <th className="px-2 py-2">차고지 주소</th>
                <th className="px-2 py-2">권역</th>
                <th className="px-2 py-2 text-right">충전기</th>
                <th className="px-2 py-2 text-right">전력량계</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && !data ? (
                <tr><td colSpan={5} className="px-2 py-8 text-center text-ash"><CircleNotch size={16} className="mx-auto animate-spin" /></td></tr>
              ) : (data?.items ?? []).length === 0 ? (
                <tr><td colSpan={5} className="px-2 py-8 text-center text-slatey">데이터가 없습니다. {canWrite ? '엑셀을 적재하세요.' : ''}</td></tr>
              ) : (
                (data?.items ?? []).map((f) => (
                  <tr key={f.facility_id} className="border-b border-hairline/60">
                    <td className="px-2 py-2 font-medium text-bone">{f.client_name ?? f.operator_name ?? '—'}</td>
                    <td className="max-w-[360px] truncate px-2 py-2 text-ash" title={f.address ?? ''}>{f.address ?? '—'}</td>
                    <td className="px-2 py-2 text-ash">{f.region ?? '—'}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-bone">{f.charger_count}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-ash">{f.meter_count}</td>
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
function Tile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-hairline bg-graphite p-4">
      <p className="text-[11px] font-medium uppercase tracking-wider text-slatey">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums text-bone">{value.toLocaleString('ko-KR')}</p>
    </div>
  )
}
