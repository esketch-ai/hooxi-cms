// SCR-01 오늘의 액션 센터 — 이슈·보고서·일정을 한 줄 리스트로 (지연 → 긴급 → D-day → 시간순)
// 데이터 조합·정렬은 DashboardPage에서 수행하고, 이 컴포넌트는 렌더만 담당한다.
import { Link } from 'react-router-dom'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonTableRows } from '../../components/Skeleton'

export type ActionKind = 'issue' | 'report' | 'schedule'

export interface ActionItem {
  kind: ActionKind
  /** 리스트 key — 유형 접두 + 원본 id */
  key: string
  title: string
  clientName?: string | null
  managerName?: string | null
  managerId?: string | null
  /** 'D+2'·'D-DAY'·'D-3' 또는 일정 시간 'HH:mm' (없으면 '') */
  dueLabel: string
  urgent: boolean
  overdue: boolean
  /** 클릭 시 직행할 화면 */
  to: string
}

const MAX_ROWS = 10

// 유형 칩 — 이슈만 rose(긴급/지연 신호), 나머지는 절제된 톤 (DESIGN 규칙)
const KIND_META: Record<ActionKind, { label: string; chipClass: string; to: string }> = {
  issue: {
    label: '이슈',
    chipClass: 'bg-rose-500/15 text-rose-700 dark:text-rose-300',
    to: '/issues',
  },
  report: {
    label: '보고서',
    chipClass: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
    to: '/reports',
  },
  schedule: {
    label: '일정',
    chipClass: 'bg-blue-500/15 text-blue-700 dark:text-blue-300',
    to: '/calendar',
  },
}

export function ActionCenter({ items, loading }: { items: ActionItem[]; loading: boolean }) {
  const visible = items.slice(0, MAX_ROWS)

  // 초과 시 "더 보기 →" — 가장 많은 유형의 화면으로 (동수면 이슈 > 보고서 > 일정)
  let moreTo: string | null = null
  if (items.length > MAX_ROWS) {
    const counts: Record<ActionKind, number> = { issue: 0, report: 0, schedule: 0 }
    items.forEach((i) => {
      counts[i.kind] += 1
    })
    const top = (['issue', 'report', 'schedule'] as ActionKind[]).reduce((a, b) =>
      counts[b] > counts[a] ? b : a,
    )
    moreTo = KIND_META[top].to
  }

  return (
    <section className="rounded-3xl border border-hairline bg-graphite p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-bone">
          오늘의 액션
          {!loading && (
            <span className="rounded-full bg-elevate px-2 py-0.5 text-[11px] font-bold text-bone">
              {items.length}건
            </span>
          )}
        </h2>
        {moreTo && (
          <Link to={moreTo} className="text-xs font-medium text-smoke hover:text-bone">
            더 보기 →
          </Link>
        )}
      </div>
      {loading ? (
        <SkeletonTableRows rows={4} />
      ) : items.length === 0 ? (
        <EmptyState
          title="오늘 처리할 일이 없습니다"
          description="지연·긴급 이슈, 임박한 보고서, 오늘 일정이 없습니다."
          className="border-0 py-10"
        />
      ) : (
        <ul className="divide-y divide-hairline">
          {visible.map((item) => {
            const meta = KIND_META[item.kind]
            const dueRose = item.overdue || item.urgent || item.dueLabel === 'D-DAY'
            return (
              <li key={item.key}>
                <Link to={item.to} className="block rounded-lg px-1 py-2.5 hover:bg-elevate">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${meta.chipClass}`}
                    >
                      {meta.label}
                    </span>
                    {item.urgent && (
                      <span className="shrink-0 rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] font-bold text-rose-700 dark:text-rose-300">
                        긴급
                      </span>
                    )}
                    <p className="min-w-0 flex-1 truncate text-sm font-medium text-bone">
                      {item.title}
                      {/* 데스크톱: 고객사·담당자를 같은 줄에 이어붙임 */}
                      <span className="hidden font-normal text-slatey sm:inline">
                        {' '}
                        · {item.clientName ?? '미지정 고객'} · {item.managerName ?? '—'}
                      </span>
                    </p>
                    {item.dueLabel && (
                      <span
                        className={`shrink-0 text-[11px] font-semibold ${
                          dueRose ? 'text-rose-700 dark:text-rose-300' : 'text-slatey'
                        }`}
                      >
                        {item.dueLabel}
                      </span>
                    )}
                  </div>
                  {/* 모바일: 고객사·담당자는 둘째 줄 (한 줄 포맷 무너짐 방지) */}
                  <p className="mt-0.5 truncate text-xs text-slatey sm:hidden">
                    {item.clientName ?? '미지정 고객'} · {item.managerName ?? '—'}
                  </p>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
