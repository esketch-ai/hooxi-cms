// 고객사 표시 공용 헬퍼 — 담당자가 확실히 인지하도록 전 메뉴에서 '지역 · 고객사명 · 구분'으로
// 일관 표시한다(오인·실수 방지). 지역·구분이 비면 그 조각은 생략한다.
//
// clientType은 tb_code CLIENT_TYPE의 라벨(예: '운수사')을 넘긴다 — useCodes('CLIENT_TYPE').labelOf
// 로 해석한 값. 코드값(TRANSPORT)이 그대로 오면 그대로 표시된다(라벨 미해석 방어).

interface ClientLike {
  company_name?: string | null
  region?: string | null
  client_type?: string | null
}

/** '지역 · 고객사명 · 구분' 한 줄 라벨. typeLabel은 해석된 구분 라벨(없으면 코드/생략). */
export function clientLabel(
  c: ClientLike | null | undefined,
  typeLabel?: string | null,
): string {
  if (!c) return ''
  const name = (c.company_name ?? '').trim()
  const region = (c.region ?? '').trim()
  const type = (typeLabel ?? c.client_type ?? '').trim()
  return [region, name, type].filter(Boolean).join(' · ')
}

/** typeLabel 해석기(useCodes('CLIENT_TYPE').labelOf)를 받아 라벨을 만드는 커링 버전 —
 *  드롭다운 map 등에서 반복 호출에 편리. */
export function makeClientLabel(labelOf: (code?: string | null) => string) {
  return (c: ClientLike | null | undefined) => clientLabel(c, c ? labelOf(c.client_type) : '')
}
