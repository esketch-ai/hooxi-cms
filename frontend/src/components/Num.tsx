// 공용 숫자 표기 규격 — 정수부는 원 크기, 소수부(최대 2자리)와 단위(tCO₂·원·% 등)는
// 0.67em(≈2/3)로 축소해 시각적으로 구분한다. tabular-nums로 자릿수 정렬.
// 오버플로 대응: 숫자 자체는 nowrap(중간 절단 오독 방지), 단위는 별도 조각이라
// 좁은 구역에서 다음 줄로 흘러내릴 수 있다(flex-wrap + min-w-0).
import type { ReactNode } from 'react'

interface NumProps {
  value?: number | string | null
  /** 뒤에 붙는 단위 표기 (예: 'tCO₂', '원', '%', '대') — 0.67em */
  unit?: string
  /** 소수 최대 자릿수 (기본 2) */
  maxFrac?: number
  /** 소수 최소 자릿수 (기본 0 — 정수는 소수부 미표시) */
  minFrac?: number
  /** 값 없음 표시 (기본 '—') */
  empty?: ReactNode
  className?: string
}

/** 숫자 문자열 헬퍼 — 콤마 그룹핑 + 소수 최대 2자리(반올림). 컴포넌트를 못 쓰는 곳용 */
export function fmt2(value?: number | string | null, maxFrac = 2): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'string' ? Number(value) : value
  if (Number.isNaN(n)) return String(value)
  return n.toLocaleString('ko-KR', { maximumFractionDigits: maxFrac })
}

export function Num({ value, unit, maxFrac = 2, minFrac = 0, empty = '—', className = '' }: NumProps) {
  if (value === null || value === undefined || value === '') {
    return <span className={className}>{empty}</span>
  }
  const n = typeof value === 'string' ? Number(value) : value
  if (Number.isNaN(n)) {
    return <span className={className}>{String(value)}</span>
  }
  const formatted = n.toLocaleString('ko-KR', {
    maximumFractionDigits: maxFrac,
    minimumFractionDigits: minFrac,
  })
  const [intPart, fracPart] = formatted.split('.')
  return (
    <span
      className={`inline-flex min-w-0 max-w-full flex-wrap items-baseline tabular-nums leading-tight ${className}`}
    >
      <span className="whitespace-nowrap">
        {intPart}
        {fracPart && <span className="text-[0.67em]">.{fracPart}</span>}
      </span>
      {unit && (
        <span className="ml-1 whitespace-nowrap text-[0.67em] font-normal opacity-80">{unit}</span>
      )}
    </span>
  )
}
