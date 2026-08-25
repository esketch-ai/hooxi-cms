// 감축량 산정(D5) — 크롤링 입력 업로드 + 전 차량 계산 결과.
import { useState } from 'react'
import { CircleNotch, UploadSimple } from '@phosphor-icons/react'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import { useImportCalcInputs, useReductionRun } from './calcApi'

const t = (v?: number | null) => (v == null ? '—' : `${v.toLocaleString('ko-KR', { maximumFractionDigits: 3 })}`)
const tco2 = (v: number) => `${v.toLocaleString('ko-KR', { maximumFractionDigits: 1 })} tCO₂`

export function CalcRunPanel() {
  const { showToast } = useToast()
  const { user } = useAuth()
  const canWrite = !!user && ['ADMIN', 'MANAGER', 'STAFF'].includes(user.role)
  const [onlyOk, setOnlyOk] = useState(true)
  const { data, isLoading } = useReductionRun(onlyOk)
  const importM = useImportCalcInputs()

  const onUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    try {
      const r = await importM.mutateAsync(files[0])
      showToast(`입력 반영 — 생성 ${r.created}·갱신 ${r.updated} · 대체도입 검증 ${r.vin_ok}·신규도입 ${r.vin_new}·확인필요 ${r.vin_warn}`, r.vin_warn > 0 ? 'info' : 'success')
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '적재에 실패했습니다.', 'danger')
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile label="계산 차량" value={`${data?.computed ?? 0}`} sub={data ? `입력 ${data.total} · 스킵 ${data.skipped}` : ''} />
        <Tile label="총 감축량(10년)" value={tco2(data?.total_reduction ?? 0)} tone />
        <Tile label="민간반영 감축량" value={tco2(data?.total_adjusted ?? 0)} tone />
        <Tile label="입력 결여(스킵)" value={`${data?.skipped ?? 0}`} />
      </div>
      <p className="text-xs text-slatey">
        eTAS·BMS 크롤링 정규화 입력(연평균 주행·연료·충전) × 방법론 상수 × 민간비율 → 계산 엔진.
        엑셀 업로드 시 차량번호로 중복 체크 후 갱신됩니다.
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <label className="flex cursor-pointer items-center gap-2 text-sm text-bone">
          <input type="checkbox" checked={onlyOk} onChange={(e) => setOnlyOk(e.target.checked)} />
          계산 성공 건만
        </label>
        {canWrite && (
          <label className="ml-auto flex cursor-pointer items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate">
            {importM.isPending ? <CircleNotch size={15} className="animate-spin" /> : <UploadSimple size={15} />}
            산정 입력 엑셀 적재
            <input type="file" accept=".xlsx" className="hidden" onChange={(e) => onUpload(e.target.files)} />
          </label>
        )}
      </div>

      <section className="rounded-2xl border border-hairline bg-graphite p-5">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[840px] text-left text-sm">
            <thead className="border-b border-hairline text-[11px] uppercase tracking-wider text-slatey">
              <tr>
                <th className="px-2 py-2">차량번호</th>
                <th className="px-2 py-2">대체도입(VIN)</th>
                <th className="px-2 py-2">운수사</th>
                <th className="px-2 py-2">연료</th>
                <th className="px-2 py-2 text-right">사업배출/년</th>
                <th className="px-2 py-2 text-right">총감축(10년)</th>
                <th className="px-2 py-2 text-right">민간비율</th>
                <th className="px-2 py-2 text-right">민간반영</th>
                <th className="px-2 py-2">권역</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && !data ? (
                <tr><td colSpan={9} className="px-2 py-8 text-center text-ash"><CircleNotch size={16} className="mx-auto animate-spin" /></td></tr>
              ) : (data?.items ?? []).length === 0 ? (
                <tr><td colSpan={9} className="px-2 py-8 text-center text-slatey">계산 결과가 없습니다. {canWrite ? '산정 입력을 적재하세요.' : ''}</td></tr>
              ) : (
                (data?.items ?? []).map((r) => (
                  <tr key={r.vehicle_no} className={`border-b border-hairline/60 ${r.status !== 'OK' ? 'opacity-60' : ''}`}>
                    <td className="px-2 py-2 font-medium text-bone">{r.vehicle_no}</td>
                    <td className="px-2 py-2">
                      {r.vin_status === 'OK' ? (
                        <span className="rounded-full border border-emerald-400/25 bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-700 dark:text-emerald-300">대체도입 검증</span>
                      ) : r.vin_status === 'NEW' ? (
                        <span className="rounded-full border border-sky-400/25 bg-sky-500/15 px-2 py-0.5 text-[11px] text-sky-700 dark:text-sky-300">신규도입</span>
                      ) : (
                        <span className="rounded-full border border-amber-400/25 bg-amber-500/15 px-2 py-0.5 text-[11px] text-amber-700 dark:text-amber-300">확인필요</span>
                      )}
                    </td>
                    <td className="px-2 py-2 text-ash">{r.operator_name ?? '—'}</td>
                    <td className="px-2 py-2 text-ash">{r.fuel ?? '—'}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-ash">{t(r.project_emission)}</td>
                    <td className="px-2 py-2 text-right tabular-nums font-semibold text-emerald-600 dark:text-emerald-400">{r.status === 'OK' ? t(r.total_reduction) : (r.reason ?? '—')}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-ash">{r.private_ratio != null ? `${(r.private_ratio * 100).toFixed(1)}%` : '—'}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-bone">{t(r.adjusted_total)}</td>
                    <td className="px-2 py-2 text-ash">{r.region ?? '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
function Tile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: boolean }) {
  return (
    <div className="rounded-2xl border border-hairline bg-graphite p-4">
      <p className="text-[11px] font-medium uppercase tracking-wider text-slatey">{label}</p>
      <p className={`mt-1 text-xl font-bold tabular-nums ${tone ? 'text-emerald-600 dark:text-emerald-400' : 'text-bone'}`}>{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-slatey">{sub}</p>}
    </div>
  )
}
