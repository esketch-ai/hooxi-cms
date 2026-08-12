// Phase 4 포털 — 프로젝트 상세(역할별 분기).
// 필드 가시성: PARTNER는 본인 차량·감축·수혜금액만. INVESTOR는 감축량·자기 계약분만(지급·원가·지급률 금지).
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, WarningCircle } from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonCards } from '../../components/Skeleton'
import { StatusBadge } from '../../components/StatusBadge'
import { useCodes } from '../../lib/api/queries'
import { fmtDate, fmtMoney, fmtServerDate } from '../../lib/format'
import { usePortalAuth } from './PortalAuthProvider'
import { usePortalProject, usePortalTimeline } from './api'
import type {
  InvestorPortalView,
  PartnerPortalView,
  PortalProjectView,
  PortalStage,
  PortalTimelinePoint,
} from './types'

/** 감축량 표기 (tCO₂) — null이면 '산정 중' */
function reductionText(value: number | null | undefined): string {
  if (value === null || value === undefined) return '산정 중'
  return `${value.toLocaleString('ko-KR')} tCO₂`
}

/** 값이 없을 때 '산정 중' 배지, 있으면 자식 렌더 */
function ValueOrPending({
  value,
  children,
}: {
  value: number | null | undefined
  children: ReactNode
}) {
  if (value === null || value === undefined) {
    return (
      <span className="inline-flex items-center rounded-full border border-amber-400/25 bg-amber-500/15 px-2 py-0.5 text-sm font-medium text-amber-700 dark:text-amber-300">
        산정 중
      </span>
    )
  }
  return <>{children}</>
}

function SummaryCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-3xl border border-hairline bg-graphite p-5">
      <p className="text-xs font-medium text-slatey">{label}</p>
      <div className="mt-2 text-2xl font-semibold text-bone">{children}</div>
    </div>
  )
}

// ── 진행 단계 (공통) ──────────────────────────────────────────────────
function StageSection({ stages }: { stages: PortalStage[] }) {
  const { labelOf } = useCodes('PROJECT_STATUS')
  const sorted = [...stages].sort((a, b) => (a.sort_order ?? 999) - (b.sort_order ?? 999))

  return (
    <section className="rounded-3xl border border-hairline bg-graphite p-5">
      <h2 className="mb-3 text-base font-bold text-bone">진행 단계</h2>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-sm">
          <thead>
            <tr className="border-b border-hairline text-xs text-slatey">
              <th className="px-2 py-2 text-left font-semibold">단계</th>
              <th className="px-2 py-2 text-left font-semibold">예정일</th>
              <th className="px-2 py-2 text-left font-semibold">완료일</th>
              <th className="px-2 py-2 text-left font-semibold">상태</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((s) => (
              <tr key={s.stage_code} className="border-b border-hairline/60 last:border-b-0">
                <td className="px-2 py-2 font-medium text-bone">{labelOf(s.stage_code)}</td>
                <td className="px-2 py-2 text-ash">{fmtDate(s.planned_date)}</td>
                <td className="px-2 py-2 text-ash">{fmtDate(s.actual_date)}</td>
                <td className="px-2 py-2">
                  {s.delayed && (
                    <span className="inline-flex items-center gap-1 rounded-full border border-rose-400/25 bg-rose-500/15 px-2 py-0.5 text-xs font-bold text-rose-700 dark:text-rose-300">
                      <WarningCircle size={12} weight="fill" />
                      지연
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

// ── PARTNER 상세 ──────────────────────────────────────────────────────
function PartnerDetail({
  view,
  timeline,
}: {
  view: PartnerPortalView
  timeline: PortalTimelinePoint[]
}) {
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-3">
        <SummaryCard label="참여 차량">
          {view.my_vehicle_count.toLocaleString('ko-KR')}대
        </SummaryCard>
        <SummaryCard label="잔여반영감축량">
          <ValueOrPending value={view.my_effective_reduction}>
            {reductionText(view.my_effective_reduction)}
          </ValueOrPending>
        </SummaryCard>
        <SummaryCard label="예상 수혜금액">
          <ValueOrPending value={view.my_expected_payout}>
            {fmtMoney(view.my_expected_payout)}
          </ValueOrPending>
        </SummaryCard>
      </div>

      <StageSection stages={view.stages} />

      <section className="rounded-3xl border border-hairline bg-graphite p-5">
        <h2 className="mb-3 text-base font-bold text-bone">추이</h2>
        {timeline.length === 0 ? (
          <p className="py-6 text-center text-sm text-slatey">기록된 추이가 없습니다.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] text-sm">
              <thead>
                <tr className="border-b border-hairline text-xs text-slatey">
                  <th className="px-2 py-2 text-left font-semibold">기준일</th>
                  <th className="px-2 py-2 text-right font-semibold">잔여반영감축량</th>
                  <th className="px-2 py-2 text-right font-semibold">예상 수혜금액</th>
                </tr>
              </thead>
              <tbody>
                {timeline.map((t, i) => (
                  <tr key={i} className="border-b border-hairline/60 last:border-b-0">
                    <td className="px-2 py-2 text-ash">{fmtServerDate(t.captured_at)}</td>
                    <td className="px-2 py-2 text-right text-bone">
                      {reductionText(t.effective_reduction)}
                    </td>
                    <td className="px-2 py-2 text-right text-bone">
                      {t.expected_payout === null || t.expected_payout === undefined
                        ? '산정 중'
                        : fmtMoney(t.expected_payout)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}

// ── INVESTOR 상세 (지급·원가·지급률 일절 표시 금지) ───────────────────
function InvestorDetail({
  view,
  timeline,
}: {
  view: InvestorPortalView
  timeline: PortalTimelinePoint[]
}) {
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-3">
        <SummaryCard label="총 잔여반영감축량">
          <ValueOrPending value={view.total_effective_reduction}>
            {reductionText(view.total_effective_reduction)}
          </ValueOrPending>
        </SummaryCard>
        <SummaryCard label="계약 수량">
          {view.my_contract && view.my_contract.quantity != null
            ? `${view.my_contract.quantity.toLocaleString('ko-KR')} tCO₂`
            : '—'}
        </SummaryCard>
        <SummaryCard label="계약 금액">
          {view.my_contract ? fmtMoney(view.my_contract.gross_revenue) : '—'}
        </SummaryCard>
      </div>

      <StageSection stages={view.stages} />

      <section className="rounded-3xl border border-hairline bg-graphite p-5">
        <h2 className="mb-3 text-base font-bold text-bone">운수사별 감축량</h2>
        {view.operators_reduction.length === 0 ? (
          <p className="py-6 text-center text-sm text-slatey">등록된 운수사 감축량이 없습니다.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] text-sm">
              <thead>
                <tr className="border-b border-hairline text-xs text-slatey">
                  <th className="px-2 py-2 text-left font-semibold">운수사</th>
                  <th className="px-2 py-2 text-right font-semibold">차량수</th>
                  <th className="px-2 py-2 text-right font-semibold">잔여반영감축량</th>
                </tr>
              </thead>
              <tbody>
                {view.operators_reduction.map((o, i) => (
                  <tr key={i} className="border-b border-hairline/60 last:border-b-0">
                    <td className="px-2 py-2 font-medium text-bone">{o.label}</td>
                    <td className="px-2 py-2 text-right text-ash">
                      {o.vehicle_count.toLocaleString('ko-KR')}대
                    </td>
                    <td className="px-2 py-2 text-right text-bone">
                      {reductionText(o.effective_reduction)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="rounded-3xl border border-hairline bg-graphite p-5">
        <h2 className="mb-3 text-base font-bold text-bone">감축량 추이</h2>
        {timeline.length === 0 ? (
          <p className="py-6 text-center text-sm text-slatey">기록된 추이가 없습니다.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[320px] text-sm">
              <thead>
                <tr className="border-b border-hairline text-xs text-slatey">
                  <th className="px-2 py-2 text-left font-semibold">기준일</th>
                  <th className="px-2 py-2 text-right font-semibold">총 잔여반영감축량</th>
                </tr>
              </thead>
              <tbody>
                {timeline.map((t, i) => (
                  <tr key={i} className="border-b border-hairline/60 last:border-b-0">
                    <td className="px-2 py-2 text-ash">{fmtServerDate(t.captured_at)}</td>
                    <td className="px-2 py-2 text-right text-bone">
                      {reductionText(t.effective_reduction)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}

/** union 판별 — INVESTOR 뷰만 operators_reduction를 가진다 */
function isInvestorView(view: PortalProjectView): view is InvestorPortalView {
  return 'operators_reduction' in view
}

export function PortalProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { me } = usePortalAuth()
  const { data: view, isLoading, isError } = usePortalProject(projectId)
  const { data: timeline } = usePortalTimeline(projectId)

  return (
    <div className="space-y-5">
      <Link
        to="/portal"
        className="inline-flex items-center gap-1.5 text-sm text-ash hover:text-bone"
      >
        <ArrowLeft size={15} />
        참여 프로젝트
      </Link>

      {isLoading ? (
        <SkeletonCards count={3} />
      ) : isError || !view ? (
        <EmptyState
          title="프로젝트를 불러오지 못했습니다"
          description="접근 권한이 없거나 잠시 문제가 발생했습니다."
        />
      ) : (
        <>
          <PageHeader
            title={view.project_name}
            actions={<StatusBadge domain="project" value={view.project_status} />}
          />
          {me?.role === 'INVESTOR' && isInvestorView(view) ? (
            <InvestorDetail view={view} timeline={timeline ?? []} />
          ) : !isInvestorView(view) ? (
            <PartnerDetail view={view} timeline={timeline ?? []} />
          ) : null}
        </>
      )}
    </div>
  )
}
