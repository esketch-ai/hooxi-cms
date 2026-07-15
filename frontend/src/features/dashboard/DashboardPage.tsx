// SCR-01 통합 현황판 — 오늘의 액션 + KPI 5카드 + 리텐션 퍼널 + 최근 활동
// 데이터: GET /dashboard/stats (routers/dashboard.py — 일괄 조회)
import { useMemo, useState } from 'react'
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
import { unwrapList } from '../../lib/api/queries'
import { dday, fmtDate, fmtMoney, fmtMonth, fmtTime } from '../../lib/format'
import type {
  DashboardStats,
  Paginated,
  ReportDelivery,
  ReportListResponse,
  Schedule,
} from '../../types'
import { useAuth } from '../../app/AuthProvider'
import { ActivityForm } from '../histories/ActivityForm'
import { ActionCenter, type ActionItem } from './ActionCenter'

const FUNNEL_COLORS = ['bg-slate-400', 'bg-blue-400', 'bg-blue-600', 'bg-emerald-500']

export function DashboardPage() {
  const [formOpen, setFormOpen] = useState(false)
  const { user } = useAuth()
  // 스코프: STAFF는 '내 것', MANAGER+는 '팀 전체'가 기본 — 액션 센터에만 적용
  const [scope, setScope] = useState<'team' | 'mine'>(() =>
    user?.role === 'STAFF' ? 'mine' : 'team',
  )

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['dashboard', 'stats'],
    queryFn: async () => {
      const { data } = await api.get<DashboardStats>('/dashboard/stats')
      return data
    },
  })

  // 당월 보고서 — 액션 센터용. ReportsPage(['reports', period])와 키 분리,
  // 조회 실패 시 빈 배열 폴백 (현황판을 막지 않는다)
  const period = fmtMonth(new Date())
  const { data: monthReports = [], isLoading: reportsLoading } = useQuery({
    queryKey: ['dashboard', 'reports', period],
    queryFn: async (): Promise<ReportDelivery[]> => {
      try {
        const { data } = await api.get<ReportListResponse>('/reports', { params: { period } })
        return data.items
      } catch {
        return []
      }
    },
    retry: false,
  })

  // 오늘의 일정 — IssuesPage와 동일한 키·fetcher (캐시 공유)
  const todayStr = fmtDate(new Date())
  const { data: todaySchedules = [], isLoading: schedulesLoading } = useQuery({
    queryKey: ['schedules', 'today'],
    queryFn: async () => {
      const { data } = await api.get<Schedule[] | Paginated<Schedule>>('/schedules', {
        params: { date_from: todayStr, date_to: todayStr },
      })
      return unwrapList(data).items
    },
    retry: false,
  })

  const kpi = data?.kpi
  const funnel = data?.funnel ?? []
  const funnelMax = Math.max(1, ...funnel.map((f) => f.count))
  const recent = (data?.recent_activities ?? []).slice(0, 8)

  // ── 오늘의 액션 조합 — 정렬: 지연 → 긴급 → D-day 오름차순 → 일정 시간순 ──
  const actionItems = useMemo<ActionItem[]>(() => {
    // dday() 라벨 → 정렬용 숫자 (지연은 음수, 기한 없음은 맨 뒤)
    const ddayNum = (due?: string | null) => {
      const d = dday(due)
      if (!d) return 9999
      if (d.label === 'D-DAY') return 0
      const n = Number(d.label.slice(2))
      return d.overdue ? -n : n
    }
    // sort: [지연 여부, 긴급 여부, D-day, 유형 순위, 일정 시각(분)]
    const rows: { item: ActionItem; sort: number[] }[] = []

    // 1) 미처리 이슈 — 긴급이거나 마감 지연/임박(D-3 이내)
    for (const issue of data?.open_issues ?? []) {
      const due = dday(issue.due_date)
      const urgent = issue.priority === 'URGENT'
      if (!urgent && !due?.overdue && !due?.imminent) continue
      rows.push({
        item: {
          kind: 'issue',
          key: `issue-${issue.history_id}`,
          title: issue.title,
          clientName: issue.client_name,
          managerName: issue.manager_name,
          managerId: issue.manager_id,
          dueLabel: due?.label ?? '',
          urgent,
          overdue: !!due?.overdue,
          to: '/issues',
        },
        sort: [due?.overdue ? 0 : 1, urgent ? 0 : 1, ddayNum(issue.due_date), 0, 0],
      })
    }

    // 2) 당월 보고서 — 미종결(SENT/CONFIRMED/CANCELED/MERGED 아님) 중 마감 지연/임박
    const doneStatuses = ['SENT', 'CONFIRMED', 'CANCELED', 'MERGED']
    for (const report of monthReports) {
      if (doneStatuses.includes(report.status)) continue
      if (!report.due_date) continue
      const due = dday(report.due_date)
      if (!due || (!due.overdue && !due.imminent)) continue
      rows.push({
        item: {
          kind: 'report',
          key: `report-${report.report_id}`,
          title: `${report.period} 월간 보고서`,
          clientName: report.client_name,
          managerName: report.manager_name,
          managerId: report.manager_id,
          dueLabel: due.label,
          urgent: false,
          overdue: due.overdue,
          to: '/reports',
        },
        sort: [due.overdue ? 0 : 1, 1, ddayNum(report.due_date), 1, 0],
      })
    }

    // 3) 오늘 일정 (PLANNED) — 같은 D-DAY 등급의 이슈·보고서 뒤, 시간 오름차순
    //    start_at은 KST 벽시계 저장 규약 → CalendarPage처럼 new Date/fmtTime 사용 (parseServerUtc 금지)
    for (const s of todaySchedules) {
      if (s.status !== 'PLANNED') continue
      const start = new Date(s.start_at)
      const timeMin = Number.isNaN(start.getTime())
        ? 0
        : start.getHours() * 60 + start.getMinutes()
      rows.push({
        item: {
          kind: 'schedule',
          key: `schedule-${s.schedule_id}`,
          title: s.title,
          clientName: s.client_name,
          managerName: s.manager_name,
          managerId: s.manager_id,
          dueLabel: fmtTime(s.start_at),
          urgent: false,
          overdue: false,
          to: '/calendar',
        },
        sort: [1, 1, 0, 2, timeMin],
      })
    }

    rows.sort((a, b) => {
      for (let i = 0; i < a.sort.length; i += 1) {
        if (a.sort[i] !== b.sort[i]) return a.sort[i] - b.sort[i]
      }
      return 0
    })
    return rows.map((r) => r.item)
  }, [data?.open_issues, monthReports, todaySchedules])

  // '내 것' 스코프 — 담당 미지정(null)은 공동 책임이므로 계속 표시
  const scopedItems = useMemo(
    () =>
      scope === 'mine'
        ? actionItems.filter((i) => !i.managerId || i.managerId === user?.user_id)
        : actionItems,
    [actionItems, scope, user?.user_id],
  )

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

      {/* 오늘의 액션 — 이슈·보고서·일정 통합 (전체 폭, KPI보다 위) */}
      <div className="flex items-center justify-end">
        <div className="flex rounded-lg border border-hairline bg-graphite p-0.5">
          {(['team', 'mine'] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setScope(s)}
              className={`rounded-md px-3 py-1 text-xs font-medium ${
                scope === s ? 'bg-primary text-on-primary' : 'text-ash hover:text-bone'
              }`}
            >
              {s === 'team' ? '팀 전체' : '내 것'}
            </button>
          ))}
        </div>
      </div>
      {/* 세 소스 중 하나라도 로딩 중이면 스켈레톤 — 빈 상태 플래시 방지 */}
      <ActionCenter items={scopedItems} loading={isLoading || reportsLoading || schedulesLoading} />

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
            to="/clients"
            compact
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
            to="/reports"
            compact
          />
          <KpiCard
            title="미처리 긴급 이슈"
            value={kpi?.urgent_open_issues ?? '—'}
            variant="danger"
            icon={<Fire size={18} />}
            to="/issues"
            compact
          />
          <KpiCard
            title="계약 검토·협의"
            value={kpi?.contract_hold_clients ?? '—'}
            sub="계약 상태 HOLD"
            icon={<Handshake size={18} />}
            to="/clients"
            compact
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
            to="/settlements"
            compact
          />
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        {/* 리텐션 퍼널 (자체 바 차트 — §10.2 4단계 매핑) */}
        <section className="rounded-3xl border border-hairline bg-graphite p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-bone">영업 파이프라인 퍼널</h2>
            <Link to="/clients" className="text-xs font-medium text-slatey hover:text-bone">
              고객사 마스터 →
            </Link>
          </div>
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
      </div>

      {/* 공용 ActivityForm 재사용 */}
      <ActivityForm open={formOpen} onClose={() => setFormOpen(false)} />
    </div>
  )
}
