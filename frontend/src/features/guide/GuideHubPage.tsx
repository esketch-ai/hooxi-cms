// 사용자 가이드 허브(/guide index) — 신입 온보딩 트랙 + 카테고리별 토픽 카드 그리드
import { Link } from 'react-router-dom'
import { PageHeader } from '../../components/PageHeader'
import { FINANCE_FEATURES, isFinanceHiddenPath } from '../../lib/featureFlags'
import { Chip } from './blocks'
import { CATEGORIES, getCategoryTopics, getTopic, isTopicHidden } from './content'

// 신입 첫 주 온보딩 트랙 — TOPICS의 핵심 6개를 순서로 엮는다(설명은 이 화면 전용 1줄).
const ONBOARDING: { topicId: string; desc: string }[] = [
  { topicId: 'start', desc: '이메일·PIN으로 로그인하고 보안 모드·테마를 익힙니다.' },
  { topicId: 'dashboard', desc: '오늘의 액션과 KPI로 하루 일과를 시작합니다.' },
  { topicId: 'clients', desc: '담당 고객사를 찾아 360° 상세로 이해합니다.' },
  { topicId: 'histories', desc: '전화·미팅·현장 방문을 활동 이력으로 남깁니다.' },
  { topicId: 'issues', desc: '이슈 보드(칸반)로 팀과 일을 나눠 처리합니다.' },
  { topicId: 'reports', desc: '월간 보고서 상태 흐름과 발송 사이클을 익힙니다.' },
]

export function GuideHubPage() {
  return (
    <div className="space-y-8">
      <PageHeader title="사용자 가이드" subtitle="메뉴별 업무 흐름과 온보딩" />

      {/* 신입 온보딩 트랙 — 첫 주 순서 */}
      <section className="space-y-3">
        <p className="text-[11px] font-bold tracking-widest text-red-600 uppercase dark:text-red-500">
          신입 온보딩 트랙 · 첫 주
        </p>
        <ol className="relative space-y-3 border-l border-hairline pl-6">
          {ONBOARDING.map((step, i) => {
            const topic = getTopic(step.topicId)
            if (!topic || isTopicHidden(topic)) return null
            return (
              <li key={step.topicId} className="relative">
                {/* 번호 배지 (좌측 라인 위에 얹음) */}
                <span className="absolute top-0.5 -left-[2.15rem] flex h-6 w-6 items-center justify-center rounded-full border border-hairline bg-elevate-strong text-[11px] font-bold text-bone">
                  {i + 1}
                </span>
                <div className="rounded-xl border border-hairline bg-graphite px-4 py-3">
                  <h3 className="text-sm font-semibold text-bone">{topic.title}</h3>
                  <p className="mt-1 text-xs leading-relaxed text-ash">{step.desc}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Link
                      to={`/guide/${topic.id}`}
                      className="rounded-full border border-hairline px-3 py-1 text-xs font-medium text-bone hover:bg-elevate"
                    >
                      가이드 보기
                    </Link>
                    {topic.featureRoute && (FINANCE_FEATURES || !isFinanceHiddenPath(topic.featureRoute)) && (
                      <Link
                        to={topic.featureRoute}
                        className="rounded-full border border-hairline px-3 py-1 text-xs font-medium text-red-600 hover:bg-elevate dark:text-red-500"
                      >
                        지금 해보기
                      </Link>
                    )}
                  </div>
                </div>
              </li>
            )
          })}
        </ol>
      </section>

      {CATEGORIES.map((cat) => {
        const topics = getCategoryTopics(cat.id)
        if (topics.length === 0) return null
        return (
          <section key={cat.id} className="space-y-3">
            <p className="text-[11px] font-bold tracking-widest text-red-600 uppercase dark:text-red-500">
              {cat.label}
            </p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {topics.map((t) => (
                <Link
                  key={t.id}
                  to={`/guide/${t.id}`}
                  className="group flex flex-col rounded-xl border border-hairline bg-graphite px-4 py-3.5 transition-colors hover:border-red-600/60 dark:hover:border-red-500/60"
                >
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-sm font-semibold text-bone">{t.title}</h3>
                    {t.accessLabel && <Chip>{t.accessLabel}</Chip>}
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-ash">{t.summary}</p>
                </Link>
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
