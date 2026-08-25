// 운행·충전 로그(D6, P1·P2) — 취합본 WIDE 업로드 → 자동 정리 뷰 + 연평균 집계.
import { useState } from 'react'
import { CircleNotch, UploadSimple, Function, CloudArrowDown } from '@phosphor-icons/react'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import { useConsolidate, useImportVehicleLogs, useImportRawLogs, useScanPreview, useScanCommit, useAggregateLogs, type AggregateResp, type ScanPreview } from './logApi'

const n = (v?: number | null) => (v == null ? '—' : v.toLocaleString('ko-KR', { maximumFractionDigits: 1 }))

export function VehicleLogPanel() {
  const { showToast } = useToast()
  const { user } = useAuth()
  const canWrite = !!user && ['ADMIN', 'MANAGER', 'STAFF'].includes(user.role)
  const [programOnly, setProgramOnly] = useState(false)
  const { data, isLoading } = useConsolidate({ program_only: programOnly })
  const importM = useImportVehicleLogs()
  const rawM = useImportRawLogs()
  const scanPvM = useScanPreview()
  const scanCommitM = useScanCommit()
  const aggM = useAggregateLogs()
  const [agg, setAgg] = useState<AggregateResp | null>(null)
  const [folder, setFolder] = useState('')
  const [preview, setPreview] = useState<ScanPreview | null>(null)

  const onUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    try {
      const r = await importM.mutateAsync(files[0])
      showToast(`로그 반영 — 차량 ${r.vehicles}·월 ${r.months} · 생성 ${r.created}·갱신 ${r.updated}`, 'success')
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '적재에 실패했습니다.', 'danger')
    }
  }

  const onUploadRaw = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    try {
      const r = await rawM.mutateAsync(files)
      const skip = r.skipped_files.length ? ` · 스킵 ${r.skipped_files.length}건` : ''
      showToast(`원본 ${r.parsed_files}/${r.files}개 반영 — 차량 ${r.vehicles}·월 ${r.months} · 생성 ${r.created}·갱신 ${r.updated}${skip}`, 'success')
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '적재에 실패했습니다.', 'danger')
    }
  }

  const onScanPreview = async () => {
    try {
      const r = await scanPvM.mutateAsync(folder.trim())
      setPreview(r)
      showToast(`스캔 완료 — 파일 ${r.parsed_files}/${r.files} · 차량 ${r.vehicles}·월 ${r.months}(미리보기, 미적재)`, 'info')
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '스캔에 실패했습니다.', 'danger')
    }
  }

  const onScanCommit = async () => {
    try {
      const r = await scanCommitM.mutateAsync(folder.trim())
      setPreview(null)
      const skip = r.skipped_files.length ? ` · 스킵 ${r.skipped_files.length}건` : ''
      showToast(`Dropbox 적재 — 파일 ${r.parsed_files}/${r.files} · 차량 ${r.vehicles}·월 ${r.months} · 생성 ${r.created}·갱신 ${r.updated}${skip}`, 'success')
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '적재에 실패했습니다.', 'danger')
    }
  }

  const onAggregate = async (commit: boolean) => {
    try {
      const r = await aggM.mutateAsync(commit)
      setAgg(r)
      showToast(
        commit
          ? `집계 반영 — 산정 입력 ${r.updated}건 갱신(연평균 ${r.aggregated}·집계불가 ${r.insufficient})`
          : `집계 계산 — 연평균 ${r.aggregated}·집계불가 ${r.insufficient}(반영 안 함)`,
        'success',
      )
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '집계에 실패했습니다.', 'danger')
    }
  }

  const months = data?.months ?? []

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile label="차량 수" value={`${data?.vehicle_count ?? 0}`} />
        <Tile label="수집 월 범위" value={months.length ? `${months[0]} ~ ${months[months.length - 1]}` : '—'} sub={`${months.length}개월`} />
        <Tile label="운행 결여" value={`${data?.missing_run ?? 0}`} tone={(data?.missing_run ?? 0) > 0 ? 'warn' : undefined} />
        <Tile label="충전 결여" value={`${data?.missing_charge ?? 0}`} tone={(data?.missing_charge ?? 0) > 0 ? 'warn' : undefined} />
      </div>
      <p className="text-xs text-slatey">
        <b className="text-ash">운수사 원본 적재(다건)</b> — eTAS <span className="font-mono">.xls</span>(운수사별 월별) 또는 BMS취합
        <span className="font-mono"> .xlsx</span>를 여러 개 한 번에 올리면 구조를 자동 판별해 로그로 정리합니다. 담당자 수작업 취합 불필요.
        <b className="text-ash"> 취합본 적재</b>는 기존 WIDE 정본(<span className="font-mono">YYYY년MM월_운행일수/운행거리/충전량</span>)용 과도기 경로.
        같은 (차량·월·출처)은 재업로드해도 안전하게 갱신(upsert). 집계는 프로그램 차량(레지스트리)만 연평균으로
        산정 입력의 사업(project) 측을 채웁니다: <span className="font-mono">(Σ지표 / Σ운행일수) × 365</span>.
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <label className="flex cursor-pointer items-center gap-2 text-sm text-bone">
          <input type="checkbox" checked={programOnly} onChange={(e) => setProgramOnly(e.target.checked)} />
          프로그램 차량만
        </label>
        {canWrite && (
          <>
            <button
              type="button"
              onClick={() => onAggregate(false)}
              disabled={aggM.isPending}
              className="ml-auto flex items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate disabled:opacity-50"
            >
              {aggM.isPending ? <CircleNotch size={15} className="animate-spin" /> : <Function size={15} />}
              연평균 집계(미리보기)
            </button>
            <button
              type="button"
              onClick={() => onAggregate(true)}
              disabled={aggM.isPending}
              className="flex items-center gap-1.5 rounded-full border border-emerald-400/30 bg-emerald-500/10 px-3.5 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-500/20 disabled:opacity-50 dark:text-emerald-300"
            >
              산정 입력 반영
            </button>
            <label className="flex cursor-pointer items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate">
              {rawM.isPending ? <CircleNotch size={15} className="animate-spin" /> : <UploadSimple size={15} />}
              운수사 원본 적재(다건)
              <input type="file" accept=".xls,.xlsx" multiple className="hidden" onChange={(e) => onUploadRaw(e.target.files)} />
            </label>
            <label className="flex cursor-pointer items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate">
              {importM.isPending ? <CircleNotch size={15} className="animate-spin" /> : <UploadSimple size={15} />}
              취합본 적재
              <input type="file" accept=".xlsx" className="hidden" onChange={(e) => onUpload(e.target.files)} />
            </label>
          </>
        )}
      </div>

      {canWrite && (
        <section className="rounded-2xl border border-hairline bg-graphite p-4">
          <div className="flex flex-wrap items-center gap-2">
            <CloudArrowDown size={17} className="text-slatey" />
            <span className="text-sm font-medium text-bone">Dropbox 폴더 자동 수집</span>
            <input
              value={folder}
              onChange={(e) => setFolder(e.target.value)}
              placeholder="예: /운행자료/eTAS (미입력 시 기본 폴더)"
              className="min-w-[240px] flex-1 rounded-lg border border-hairline bg-elevate px-3 py-1.5 text-sm text-bone placeholder:text-slatey/60"
            />
            <button
              type="button"
              onClick={onScanPreview}
              disabled={scanPvM.isPending}
              className="flex items-center gap-1.5 rounded-full border border-hairline px-3.5 py-1.5 text-sm font-medium text-bone hover:bg-elevate disabled:opacity-50"
            >
              {scanPvM.isPending ? <CircleNotch size={15} className="animate-spin" /> : <CloudArrowDown size={15} />}
              스캔(미리보기)
            </button>
            <button
              type="button"
              onClick={onScanCommit}
              disabled={scanCommitM.isPending || !preview}
              className="flex items-center gap-1.5 rounded-full border border-emerald-400/30 bg-emerald-500/10 px-3.5 py-1.5 text-sm font-medium text-emerald-700 hover:bg-emerald-500/20 disabled:opacity-40 dark:text-emerald-300"
            >
              적재
            </button>
          </div>
          {preview && (
            <p className="mt-2 text-xs text-slatey">
              <b className="text-ash">{preview.folder}</b> — .xls/.xlsx {preview.parsed_files}/{preview.files}개 파싱 ·
              차량 {preview.vehicles} · 월 {preview.months} · 로그 {preview.total.toLocaleString('ko-KR')}행
              {preview.skipped_files.length > 0 && ` · 스킵 ${preview.skipped_files.length}건`}
              {' '}→ '적재' 시 (차량·월·출처) 기준으로 반영됩니다.
            </p>
          )}
          <p className="mt-1 text-[11px] text-slatey">
            담당자가 지정 폴더(하위 포함)에 eTAS·BMS 원본을 저장만 하면 스캔해 로그로 정리합니다. 저장소 루트 밖 폴더는 차단.
          </p>
        </section>
      )}

      {agg && (
        <section className="rounded-2xl border border-emerald-400/20 bg-emerald-500/[0.04] p-4">
          <p className="text-sm font-medium text-bone">
            연평균 집계 결과 — 연평균 산정 {agg.aggregated}건 · 집계불가 {agg.insufficient}건
            {agg.updated > 0 && ` · 산정 입력 ${agg.updated}건 반영`}
          </p>
          <p className="mt-1 text-xs text-slatey">집계불가 = 운행일수/거리 결여(계산 스킵). 프로그램 차량만 대상.</p>
        </section>
      )}

      <section className="rounded-2xl border border-hairline bg-graphite p-5">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm" style={{ minWidth: `${360 + months.length * 220}px` }}>
            <thead className="border-b border-hairline text-[11px] uppercase tracking-wider text-slatey">
              <tr>
                <th className="sticky left-0 z-10 bg-graphite px-2 py-2">차량번호</th>
                <th className="px-2 py-2">운수사</th>
                {months.map((m) => (
                  <th key={m} className="px-2 py-2 text-center" colSpan={3}>{m}</th>
                ))}
              </tr>
              <tr className="text-[10px]">
                <th className="sticky left-0 z-10 bg-graphite px-2 py-1"></th>
                <th className="px-2 py-1"></th>
                {months.map((m) => (
                  <FragmentHead key={m} />
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading && !data ? (
                <tr><td colSpan={2 + months.length * 3} className="px-2 py-8 text-center text-ash"><CircleNotch size={16} className="mx-auto animate-spin" /></td></tr>
              ) : (data?.vehicles ?? []).length === 0 ? (
                <tr><td colSpan={2 + months.length * 3} className="px-2 py-8 text-center text-slatey">로그가 없습니다. {canWrite ? '취합본을 적재하세요.' : ''}</td></tr>
              ) : (
                (data?.vehicles ?? []).map((v) => (
                  <tr key={v.vehicle_no} className="border-b border-hairline/60">
                    <td className="sticky left-0 z-10 bg-graphite px-2 py-2 font-medium text-bone">
                      {v.vehicle_no}
                      {!v.has_charge && <span className="ml-1 rounded-full border border-amber-400/25 bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-700 dark:text-amber-300">충전 결여</span>}
                      {!v.has_run && <span className="ml-1 rounded-full border border-rose-400/25 bg-rose-500/15 px-1.5 py-0.5 text-[10px] text-rose-700 dark:text-rose-300">운행 결여</span>}
                    </td>
                    <td className="px-2 py-2 text-ash">{v.operator_name ?? '—'}</td>
                    {months.map((m) => {
                      const cell = v.months[m]
                      return (
                        <FragmentCell
                          key={m}
                          days={cell?.operating_days ?? null}
                          dist={cell?.distance_km ?? null}
                          kwh={cell?.charge_kwh ?? null}
                        />
                      )
                    })}
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

function FragmentHead() {
  return (
    <>
      <th className="px-2 py-1 text-right font-normal text-slatey">일수</th>
      <th className="px-2 py-1 text-right font-normal text-slatey">운행km</th>
      <th className="px-2 py-1 text-right font-normal text-slatey">충전kWh</th>
    </>
  )
}

function FragmentCell({ days, dist, kwh }: { days: number | null; dist: number | null; kwh: number | null }) {
  return (
    <>
      <td className="px-2 py-2 text-right tabular-nums text-ash">{n(days)}</td>
      <td className="px-2 py-2 text-right tabular-nums text-ash">{n(dist)}</td>
      <td className={`px-2 py-2 text-right tabular-nums ${kwh == null ? 'text-slatey/50' : 'text-ash'}`}>{n(kwh)}</td>
    </>
  )
}

function Tile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: 'warn' }) {
  return (
    <div className="rounded-2xl border border-hairline bg-graphite p-4">
      <p className="text-[11px] font-medium uppercase tracking-wider text-slatey">{label}</p>
      <p className={`mt-1 text-xl font-bold tabular-nums ${tone === 'warn' ? 'text-amber-600 dark:text-amber-400' : 'text-bone'}`}>{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-slatey">{sub}</p>}
    </div>
  )
}
