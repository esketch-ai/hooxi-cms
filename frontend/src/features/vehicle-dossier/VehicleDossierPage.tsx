// 차량 통합 상세(개편 P5) — 한 vehicle_no의 전 생애를 한 화면에.
// 파편화된 7개 모델(보유·참여·레지스트리·산정·3단계·로그·재무)을 차량번호로 묶어 본다.
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Bus } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { useVehicleDossier } from './api'

const tco2 = (v?: number | null) => (v == null ? '—' : `${v.toLocaleString('ko-KR', { maximumFractionDigits: 1 })} tCO₂`)
const num = (v?: number | null) => (v == null ? '—' : v.toLocaleString('ko-KR', { maximumFractionDigits: 1 }))
const won = (v?: number | null) => (v == null ? '—' : `${Math.round(v).toLocaleString('ko-KR')}원`)
const pct = (v?: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)

function Section({ title, children, note }: { title: string; children: React.ReactNode; note?: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-hairline bg-graphite p-5">
      <div className="mb-3 flex items-baseline gap-2">
        <h2 className="text-sm font-semibold text-bone">{title}</h2>
        {note && <span className="text-[11px] text-slatey">{note}</span>}
      </div>
      {children}
    </section>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[11px] text-slatey">{label}</dt>
      <dd className="text-sm text-bone tabular-nums">{children}</dd>
    </div>
  )
}

const STAGE_LABEL: Record<string, string> = { PLANNED: '예상', MONITORING: '모니터링', FINAL: '최종' }

export function VehicleDossierPage() {
  const { vehicleNo = '' } = useParams<{ vehicleNo: string }>()
  const decoded = decodeURIComponent(vehicleNo)
  const { data, isLoading } = useVehicleDossier(decoded)

  return (
    <div className="animate-fade-in space-y-4">
      <Link to="/asset-vehicles" className="inline-flex items-center gap-1 text-xs text-slatey hover:text-ash">
        <ArrowLeft size={13} /> 전기버스 자산으로
      </Link>
      <PageHeader title={`차량 통합 상세 · ${decoded}`} subtitle="보유·참여·레지스트리·산정·3단계·운행/충전·재무를 차량번호로 묶은 전 생애 뷰" />

      {isLoading && !data ? (
        <div className="py-16 text-center text-slatey">불러오는 중…</div>
      ) : !data?.found ? (
        <div className="rounded-2xl border border-hairline bg-graphite px-4 py-12 text-center">
          <Bus size={28} className="mx-auto mb-2 text-slatey" />
          <p className="text-sm text-slatey">이 차량번호로 등록된 데이터가 없습니다.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {/* 보유 차량 */}
          <Section title="보유 차량" note={`${data.owned.length}건(내연·전기 공존 가능)`}>
            {data.owned.length === 0 ? <p className="text-sm text-slatey">보유 차량 원장에 없음(참여만 등록됨).</p> : (
              <div className="space-y-3">
                {data.owned.map((o) => (
                  <div key={o.vehicle_id} className="grid grid-cols-2 gap-x-6 gap-y-2 rounded-xl border border-hairline/60 p-3 sm:grid-cols-4">
                    <Field label="운수사">{o.client_id ? <Link to={`/clients/${o.client_id}`} className="hover:underline">{o.operator_name ?? '이동'}</Link> : (o.operator_name ?? '—')}</Field>
                    <Field label="차명">{o.model_name ?? '—'}</Field>
                    <Field label="연료">{o.fuel ?? '—'}</Field>
                    <Field label="연식">{o.model_year ?? '—'}</Field>
                    <Field label="차대번호">{o.chassis_no ?? '—'}</Field>
                    <Field label="차종">{o.vehicle_class ?? '—'}</Field>
                    <Field label="승차정원">{o.seating_capacity ?? '—'}</Field>
                    <Field label="상태">{o.status ?? '—'}</Field>
                  </div>
                ))}
              </div>
            )}
          </Section>

          {/* 감축 참여 */}
          <Section title="감축 참여" note={`${data.participations.length}개 사업`}>
            {data.participations.length === 0 ? <p className="text-sm text-slatey">참여 이력 없음(미참여).</p> : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="border-b border-hairline text-[11px] uppercase tracking-wider text-slatey">
                    <tr><th className="px-2 py-1.5">사업</th><th className="px-2 py-1.5">단계</th><th className="px-2 py-1.5">도입구분</th><th className="px-2 py-1.5 text-right">예상 감축</th><th className="px-2 py-1.5 text-right">최종 감축</th><th className="px-2 py-1.5 text-right">예상 지급</th></tr>
                  </thead>
                  <tbody>
                    {data.participations.map((p, i) => (
                      <tr key={i} className="border-b border-hairline/60">
                        <td className="px-2 py-1.5">{p.project_id ? <Link to={`/projects/${p.project_id}`} className="text-ash hover:text-bone hover:underline">{p.project_name ?? '사업'}</Link> : (p.project_name ?? '—')}</td>
                        <td className="px-2 py-1.5 text-ash">{p.project_status ?? '—'}</td>
                        <td className="px-2 py-1.5 text-ash">{p.introduction_type ?? '—'}</td>
                        <td className="px-2 py-1.5 text-right text-ash">{tco2(p.total_reduction)}</td>
                        <td className="px-2 py-1.5 text-right text-bone">{tco2(p.effective_reduction)}</td>
                        <td className="px-2 py-1.5 text-right text-ash">{won(p.expected_payout)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          {/* 3단계 감축량 */}
          <Section title="3단계 감축량" note="예상=사업 · 모니터링=워크벤치 · 최종=발급확정">
            <div className="grid grid-cols-3 gap-3">
              {(['PLANNED', 'MONITORING', 'FINAL'] as const).map((st) => (
                <div key={st} className="rounded-xl border border-hairline/60 p-3 text-center">
                  <p className="text-[11px] text-slatey">{STAGE_LABEL[st]}</p>
                  <p className="mt-1 text-base font-bold tabular-nums text-bone">{tco2(data.stages[st]?.total_reduction)}</p>
                </div>
              ))}
            </div>
          </Section>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* 산정 입력 */}
            <Section title="산정 입력(연평균)" note={<Link to="/registry" className="hover:underline">워크벤치 →</Link>}>
              {!data.calc_input ? <p className="text-sm text-slatey">산정 입력 없음.</p> : (
                <dl className="grid grid-cols-2 gap-x-6 gap-y-2">
                  <Field label="연료">{data.calc_input.fuel ?? '—'}</Field>
                  <Field label="도입구분">{data.calc_input.introduction_type ?? '—'}</Field>
                  <Field label="베이스라인 주행">{num(data.calc_input.baseline_distance)}</Field>
                  <Field label="베이스라인 연료">{num(data.calc_input.baseline_fuel)}</Field>
                  <Field label="사업 주행">{num(data.calc_input.project_distance)}</Field>
                  <Field label="사업 충전">{num(data.calc_input.project_kwh)}</Field>
                  <Field label="전기차 등록연도">{data.calc_input.ev_reg_year ?? '—'}</Field>
                  <Field label="민간비율">{pct(data.calc_input.private_ratio)}</Field>
                </dl>
              )}
            </Section>

            {/* 재무 */}
            <Section title="재무(민간투자비율 근거)">
              {!data.finance ? <p className="text-sm text-slatey">재무 데이터 없음.</p> : (
                <dl className="grid grid-cols-2 gap-x-6 gap-y-2">
                  <Field label="차량가액">{won(data.finance.vehicle_value)}</Field>
                  <Field label="자부담금">{won(data.finance.self_payment)}</Field>
                  <Field label="전기차보조금">{won(data.finance.ev_subsidy)}</Field>
                  <Field label="민간비율">{pct(data.finance.private_ratio)}</Field>
                  <Field label="공공비율">{pct(data.finance.public_ratio)}</Field>
                </dl>
              )}
            </Section>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* 운행·충전 로그 요약 */}
            <Section title="운행·충전 로그">
              {!data.log_summary ? <p className="text-sm text-slatey">수집 로그 없음.</p> : (
                <dl className="grid grid-cols-2 gap-x-6 gap-y-2">
                  <Field label="수집 기간">{data.log_summary.month_from} ~ {data.log_summary.month_to}</Field>
                  <Field label="개월 수">{data.log_summary.month_count}</Field>
                  <Field label="출처">{data.log_summary.sources.join(', ') || '—'}</Field>
                  <Field label="충전량 보유">{data.log_summary.has_charge ? '있음' : <span className="text-amber-600 dark:text-amber-400">결여</span>}</Field>
                  <Field label="누적 운행거리">{num(data.log_summary.total_distance)} km</Field>
                  <Field label="누적 충전량">{num(data.log_summary.total_charge)} kWh</Field>
                </dl>
              )}
            </Section>

            {/* 레지스트리 */}
            <Section title="감축 레지스트리(KISA)">
              {data.registry.length === 0 ? <p className="text-sm text-slatey">레지스트리 없음.</p> : (
                <div className="space-y-2">
                  {data.registry.map((r, i) => (
                    <div key={i} className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl border border-hairline/60 p-2.5 text-sm">
                      <span className="rounded-full border border-hairline bg-elevate px-2 py-0.5 text-[11px] text-ash">{r.role ?? '—'}</span>
                      <span className="text-slatey">도입: <span className="text-ash">{r.introduction_type ?? '—'}</span></span>
                      <span className="text-slatey">VIN: <span className="font-mono text-ash">{r.vin ?? '—'}</span></span>
                    </div>
                  ))}
                </div>
              )}
            </Section>
          </div>
        </div>
      )}
    </div>
  )
}
