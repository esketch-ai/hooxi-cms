// SCR-01 통합 현황판 — KPI 5카드 + 리텐션 퍼널 + 최근 활동 + 미처리 이슈
// 데이터: GET /dashboard/stats (routers/dashboard.py — 일괄 조회)
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Buildings,
  CurrencyKrw,
  FileText,
  Fire,
  Handshake,
  MapTrifold,
  Plus,
  SquaresFour,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { KpiCard } from '../../components/KpiCard'
import { SensitiveData } from '../../components/SensitiveData'
import { Timeline } from '../../components/Timeline'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonKpi, SkeletonTableRows } from '../../components/Skeleton'
import { api } from '../../lib/api/client'
import { dday, elapsedServer, fmtMoney } from '../../lib/format'
import type { DashboardStats } from '../../types'
import { ActivityForm } from '../histories/ActivityForm'

const FUNNEL_COLORS = ['bg-slate-400', 'bg-blue-400', 'bg-blue-600', 'bg-emerald-500']

export function DashboardPage() {
  const [formOpen, setFormOpen] = useState(false)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['dashboard', 'stats'],
    queryFn: async () => {
      const { data } = await api.get<DashboardStats>('/dashboard/stats')
      return data
    },
  })

  const kpi = data?.kpi
  const funnel = data?.funnel ?? []
  const funnelMax = Math.max(1, ...funnel.map((f) => f.count))
  const recent = (data?.recent_activities ?? []).slice(0, 8)
  const openIssues = (data?.open_issues ?? []).slice(0, 6)

  if (isError) {
    return (
      <div className="animate-fade-in space-y-5">
        <PageHeader title="통합 현황판" subtitle="팀 전체 KPI · 파이프라인 · 최근 활동" />
        <EmptyState
          icon={<SquaresFour size={36} />}
          title="현황판을 불러오지 못했습니다"
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
      </div>
    )
  }

  return (
    <div className="animate-fade-in space-y-5">
      <PageHeader
        title="통합 현황판"
        subtitle={`팀 전체 KPI · 파이프라인 · 최근 활동${data ? ` (${data.period})` : ''}`}
        actions={
          <>
            {/* SCR-01 → SCR-09 지도 진입 링크 (§2.1 보조 화면) */}
            <Link
              to="/map"
              className="hidden items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate sm:flex"
            >
              <MapTrifold size={16} />
              관제 지도
            </Link>
            <button
              type="button"
              onClick={() => setFormOpen(true)}
              className="hidden items-center gap-1.5 rounded-full bg-primary px-3.5 py-2 text-sm font-medium text-on-primary hover:opacity-90 sm:flex"
            >
              <Plus size={16} weight="bold" />
              신규 이력 등록
            </button>
          </>
        }
      />

      {/* KPI 5카드 */}
      {isLoading ? (
        <SkeletonKpi count={5} />
      ) : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <KpiCard
            title="관리 고객사"
            value={kpi?.total_clients ?? '—'}
            sub={
              kpi != null
                ? `이번 달 신규 ${kpi.client_delta >= 0 ? '+' : ''}${kpi.client_delta}`
                : undefined
            }
            icon={<Buildings size={18} />}
          />
          <KpiCard
            title="당월 보고서"
            value={
              kpi ? (
                <span>
                  {kpi.report_sent}
                  <span className="text-base font-semibold text-slatey">
                    /{kpi.report_target}
                  </span>
                </span>
              ) : (
                '—'
              )
            }
            sub="발송 완료 / 대상"
            icon={<FileText size={18} />}
          />
          <KpiCard
            title="미처리 긴급 이슈"
            value={kpi?.urgent_open_issues ?? '—'}
            variant="danger"
            icon={<Fire size={18} />}
          />
          <KpiCard
            title="계약 검토·협의"
            value={kpi?.contract_hold_clients ?? '—'}
            sub="계약 상태 HOLD"
            icon={<Handshake size={18} />}
          />
          <KpiCard
            title="당월 예상 청구액"
            value={
              kpi?.expected_billing_amount != null ? (
                <SensitiveData type="money" value={fmtMoney(kpi.expected_billing_amount)} />
              ) : (
                '미정'
              )
            }
            variant="dark"
            icon={<CurrencyKrw size={18} />}
          />
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-3">
        {/* 리텐션 퍼널 (자체 바 차트 — §10.2 4단계 매핑) */}
        <section className="rounded-3xl border border-hairline bg-graphite p-5">
          <h2 className="mb-4 text-sm font-semibold text-bone">영업 파이프라인 퍼널</h2>
          {isLoading ? (
            <SkeletonTableRows rows={4} />
          ) : funnel.length === 0 ? (
            <EmptyState
              title="퍼널 데이터가 없습니다"
              description="리텐션 단계가 기록되면 집계가 표시됩니다."
              className="border-0 py-10"
            />
          ) : (
            <div className="space-y-3">
              {funnel.map((step, i) => (
                <div key={step.stage}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="font-medium text-ash">{step.stage}</span>
                    <span className="font-bold text-bone">{step.count}</span>
                  </div>
                  <div className="h-5 overflow-hidden rounded bg-elevate">
                    <div
                      className={`h-full rounded transition-all ${FUNNEL_COLORS[i % FUNNEL_COLORS.length]}`}
                      style={{ width: `${Math.round((step.count / funnelMax) * 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* 최근 활동 타임라인 (전사, 작성자 표기) */}
        <section className="rounded-3xl border border-hairline bg-graphite p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-bone">최근 활동</h2>
            <Link
              to="/histories"
              className="text-xs font-medium text-smoke hover:text-bone"
            >
              전체 보기 →
            </Link>
          </div>
          {isLoading ? (
            <SkeletonTableRows rows={4} />
          ) : recent.length === 0 ? (
            <EmptyState
              title="최근 활동이 없습니다"
              description="첫 활동 이력을 등록해 보세요."
              className="border-0 py-10"
            />
          ) : (
            <Timeline items={recent} />
          )}
        </section>

        {/* 미처리 이슈 → /issues 딥링크 */}
        <section className="rounded-3xl border border-hairline bg-graphite p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-bone">미처리 이슈</h2>
            <Link
              to="/issues"
              className="text-xs font-medium text-smoke hover:text-bone"
            >
              이슈 보드 →
            </Link>
          </div>
          {isLoading ? (
            <SkeletonTableRows rows={4} />
          ) : openIssues.length === 0 ? (
            <EmptyState
              title="미처리 이슈가 없습니다"
              description="모든 이슈가 처리되었습니다."
              className="border-0 py-10"
            />
          ) : (
            <ul className="divide-y divide-hairline">
              {openIssues.map((issue) => {
                const due = dday(issue.due_date)
                return (
                  <li key={issue.history_id}>
                    <Link to="/issues" className="block rounded-lg px-1 py-2.5 hover:bg-elevate">
                      <div className="flex items-center gap-1.5">
                        {issue.priority === 'URGENT' && (
                          <span className="shrink-0 rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] font-bold text-rose-700 dark:text-rose-300">
                            긴급
                          </span>
                        )}
                        <p className="min-w-0 flex-1 truncate text-sm font-medium text-bone">
                          {issue.title}
                        </p>
                        {due && (
                          <span
                            className={`shrink-0 text-[11px] font-semibold ${
                              due.overdue || due.imminent ? 'text-rose-700 dark:text-rose-300' : 'text-slatey'
                            }`}
                          >
                            {due.label}
                          </span>
                        )}
                      </div>
                      <p className="mt-0.5 text-xs text-slatey">
                        {issue.client_name ?? '미지정 고객'} · {issue.manager_name ?? '—'} ·{' '}
                        {elapsedServer(issue.created_at)}
                      </p>
                    </Link>
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      </div>

      {/* 공용 ActivityForm 재사용 */}
      <ActivityForm open={formOpen} onClose={() => setFormOpen(false)} />
    </div>
  )
}
