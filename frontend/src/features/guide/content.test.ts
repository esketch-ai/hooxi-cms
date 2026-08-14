import { describe, expect, it } from 'vitest'
import { CATEGORIES, TOPICS, getCategoryTopics, getTopic } from './content'

// ※ Body는 렌더(JSX 실행)하지 않는다 — DOM/React가 없는 node 환경. 데이터·헬퍼만 검증한다.

const topicIds = new Set(TOPICS.map((t) => t.id))
const categoryIds = new Set(CATEGORIES.map((c) => c.id))

describe('getTopic / getCategoryTopics', () => {
  it('getTopic — 존재하는 id는 해당 토픽, 없는 id는 undefined', () => {
    expect(getTopic('start')?.id).toBe('start')
    expect(getTopic('__none__')).toBeUndefined()
  })
  it('getCategoryTopics — 해당 카테고리의 토픽만 반환', () => {
    const work = getCategoryTopics('work')
    expect(work.length).toBeGreaterThan(0)
    for (const t of work) expect(t.categoryId).toBe('work')
    expect(getCategoryTopics('__none__')).toEqual([])
  })
})

describe('레지스트리 무결성', () => {
  it('(a) 모든 topic.id는 유일하다', () => {
    expect(topicIds.size).toBe(TOPICS.length)
  })

  it('(b) 모든 topic.categoryId는 CATEGORIES에 존재한다', () => {
    for (const t of TOPICS) expect(categoryIds.has(t.categoryId)).toBe(true)
  })

  it('(c) 모든 related id는 실재하는 topicId를 가리킨다', () => {
    for (const t of TOPICS) {
      for (const r of t.related ?? []) {
        expect(topicIds.has(r), `${t.id} → related ${r}`).toBe(true)
      }
    }
  })

  it('(d) featureRoute는 지정 시 "/"로 시작한다', () => {
    // 참고: featureRoute의 전역 유일성은 요구하지 않는다 —
    // 한 화면(예: /clients)에 여러 토픽(clients·fleet-import: 보유 차량 탭)이 정당하게 매핑된다.
    const routes = TOPICS.map((t) => t.featureRoute).filter((r): r is string => !!r)
    for (const r of routes) expect(r.startsWith('/')).toBe(true)
  })

  it('(e) 각 CATEGORY에는 최소 1개의 토픽이 있다', () => {
    for (const c of CATEGORIES) {
      expect(getCategoryTopics(c.id).length, `category ${c.id}`).toBeGreaterThan(0)
    }
  })
})
