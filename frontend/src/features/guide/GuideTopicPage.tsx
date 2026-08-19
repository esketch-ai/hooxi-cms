// 사용자 가이드 토픽 상세(/guide/:topicId)
// eyebrow+title 헤더 + '이 기능 열기' 딥링크 + Body + 관련 가이드 + 이전/다음 네비.
// 없는 id는 허브로 리다이렉트.
import { ArrowRight } from '@phosphor-icons/react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { FINANCE_FEATURES, isFinanceHiddenPath } from '../../lib/featureFlags'
import { Chip } from './blocks'
import { CATEGORIES, getTopic, isTopicHidden, visibleTopics } from './content'

export function GuideTopicPage() {
  const { topicId } = useParams<{ topicId: string }>()
  const topic = topicId ? getTopic(topicId) : undefined

  // 없는 id, 또는 현재 배포에서 은닉된 토픽(재무 OFF)은 허브로 리다이렉트
  if (!topic || isTopicHidden(topic)) return <Navigate to="/guide" replace />

  const category = CATEGORIES.find((c) => c.id === topic.categoryId)
  const { Body } = topic

  // 노출 토픽 배열 순서 기준 이전/다음(카테고리 무시, 양끝은 한쪽 생략)
  const nav = visibleTopics()
  const idx = nav.findIndex((t) => t.id === topic.id)
  const prev = idx > 0 ? nav[idx - 1] : undefined
  const next = idx >= 0 && idx < nav.length - 1 ? nav[idx + 1] : undefined

  // 관련 가이드 — 유효하고 노출되는 id만 해석
  const related = (topic.related ?? [])
    .map((id) => getTopic(id))
    .filter((t): t is NonNullable<typeof t> => !!t && !isTopicHidden(t))

  return (
    <div className="max-w-3xl space-y-4">
      {/* 브레드크럼 */}
      <nav className="text-xs text-slatey" aria-label="브레드크럼">
        <Link to="/guide" className="hover:text-ash">
          가이드
        </Link>
        {category && <span className="mx-1.5">/</span>}
        {category && <span>{category.label}</span>}
        <span className="mx-1.5">/</span>
        <span className="text-ash">{topic.title}</span>
      </nav>

      {/* 헤더 (기존 Sec 스타일 재현) + 딥링크 */}
      <div className="flex flex-col gap-3 border-b border-hairline pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-0.5 text-[11px] font-bold tracking-widest text-red-600 uppercase dark:text-red-500">
            {topic.eyebrow}
          </p>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-bone">{topic.title}</h2>
            {topic.accessLabel && <Chip>{topic.accessLabel}</Chip>}
          </div>
        </div>
        {topic.featureRoute && (FINANCE_FEATURES || !isFinanceHiddenPath(topic.featureRoute)) && (
          <Link
            to={topic.featureRoute}
            className="inline-flex shrink-0 items-center gap-1.5 self-start rounded-full border border-hairline bg-elevate px-4 py-2 text-sm font-medium text-bone transition-colors hover:border-red-600/60 sm:self-auto dark:hover:border-red-500/60"
          >
            이 기능 열기
            <ArrowRight size={15} weight="bold" className="text-red-600 dark:text-red-500" />
          </Link>
        )}
      </div>

      {/* 본문 (기존 Sec 콘텐츠 래퍼 클래스 그대로) */}
      <div className="space-y-2 text-sm leading-relaxed text-ash [&_b]:text-bone [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5 [&_li]:marker:text-slatey">
        <Body />
      </div>

      {/* 관련 가이드 */}
      {related.length > 0 && (
        <section className="border-t border-hairline pt-4">
          <p className="mb-2 text-[11px] font-bold tracking-widest text-slatey uppercase">
            관련 가이드
          </p>
          <div className="flex flex-wrap gap-2">
            {related.map((r) => (
              <Link
                key={r.id}
                to={`/guide/${r.id}`}
                className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-graphite px-3 py-1.5 text-xs font-medium text-bone transition-colors hover:border-red-600/60 dark:hover:border-red-500/60"
              >
                {r.title}
                {r.accessLabel && <Chip>{r.accessLabel}</Chip>}
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* 이전/다음 */}
      <nav
        className="flex items-stretch gap-3 border-t border-hairline pt-4"
        aria-label="이전 다음 가이드"
      >
        {prev ? (
          <Link
            to={`/guide/${prev.id}`}
            className="group flex flex-1 flex-col rounded-xl border border-hairline bg-graphite px-4 py-3 transition-colors hover:border-red-600/60 dark:hover:border-red-500/60"
          >
            <span className="text-[11px] text-slatey">← 이전</span>
            <span className="mt-0.5 truncate text-sm font-semibold text-bone">{prev.title}</span>
          </Link>
        ) : (
          <span className="flex-1" />
        )}
        {next ? (
          <Link
            to={`/guide/${next.id}`}
            className="group flex flex-1 flex-col rounded-xl border border-hairline bg-graphite px-4 py-3 text-right transition-colors hover:border-red-600/60 dark:hover:border-red-500/60"
          >
            <span className="text-[11px] text-slatey">다음 →</span>
            <span className="mt-0.5 truncate text-sm font-semibold text-bone">{next.title}</span>
          </Link>
        ) : (
          <span className="flex-1" />
        )}
      </nav>
    </div>
  )
}
