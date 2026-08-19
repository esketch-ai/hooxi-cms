import { describe, expect, it } from 'vitest'
import { FINANCE_FEATURES, isFinanceHiddenPath } from '../../lib/featureFlags'
import { TOPICS, getCategoryTopics, isTopicHidden, visibleTopics } from './content'

// 가이드 토픽 은닉 게이팅 순수 로직.
// ※ FINANCE_FEATURES는 빌드타임 상수라 테스트 env(플래그 미설정)에서는 항상 ON(true)이다.
//   따라서 (1) ON 경로 회귀 0은 isTopicHidden/visibleTopics로 직접 검증하고,
//   (2) OFF에서의 은닉 판정은 경로 매칭 로직(isFinanceHiddenPath + featureRoute 유무 조합)으로 검증한다.

// OFF일 때 은닉돼야 하는 토픽(설계 기준): featureRoute가 재무 은닉 경로인 5개.
const EXPECTED_HIDDEN_IDS = ['finance-ledger', 'asset-report', 'settlements', 'buyers', 'portal-accounts']

describe('isTopicHidden / visibleTopics (현재 빌드 = ON)', () => {
  it('테스트 env에서 FINANCE_FEATURES는 ON(true)', () => {
    expect(FINANCE_FEATURES).toBe(true)
  })

  it('ON 경로 회귀 0 — 어떤 토픽도 은닉되지 않는다', () => {
    for (const t of TOPICS) expect(isTopicHidden(t)).toBe(false)
  })

  it('ON — visibleTopics는 전체 토픽과 동일', () => {
    expect(visibleTopics()).toEqual(TOPICS)
  })

  it('ON — getCategoryTopics는 카테고리 토픽을 그대로 반환(누락 없음)', () => {
    for (const t of TOPICS) {
      const ids = getCategoryTopics(t.categoryId).map((x) => x.id)
      expect(ids).toContain(t.id)
    }
  })
})

describe('OFF 은닉 판정 로직(경로 매칭)', () => {
  // isTopicHidden의 OFF 분기와 동치인 순수 판정: featureRoute가 있고 재무 은닉 경로일 때 은닉.
  const wouldHideWhenOff = (route?: string): boolean => !!route && isFinanceHiddenPath(route)

  it('설계상 은닉 대상 5개 토픽은 OFF에서 은닉된다', () => {
    for (const id of EXPECTED_HIDDEN_IDS) {
      const t = TOPICS.find((x) => x.id === id)
      expect(t, `topic ${id} 존재`).toBeTruthy()
      expect(wouldHideWhenOff(t!.featureRoute), `${id} 은닉`).toBe(true)
    }
  })

  it('그 외 토픽은 OFF에서도 노출된다(과잉 은닉 없음)', () => {
    const hiddenSet = new Set(EXPECTED_HIDDEN_IDS)
    for (const t of TOPICS) {
      if (hiddenSet.has(t.id)) continue
      expect(wouldHideWhenOff(t.featureRoute), `${t.id} 노출`).toBe(false)
    }
  })

  it('featureRoute 없는 토픽(start·faq 등)은 은닉 대상이 아니다', () => {
    for (const t of TOPICS.filter((x) => !x.featureRoute)) {
      expect(wouldHideWhenOff(t.featureRoute)).toBe(false)
    }
  })
})
