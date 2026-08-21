// 자체 SVG 차트 프리미티브(무의존) — 경영 관찰(Executive View) 전용 경량 3종.
// 다크/라이트는 currentColor·시맨틱 클래스에 위임, 반응형은 viewBox 스케일링.
// 모든 요소는 클릭 가능(개요 드로어 드릴다운) — onSelect 콜백으로 위임한다.
import { useMemo, useState } from 'react'

const nf = (n: number) => n.toLocaleString('ko-KR', { maximumFractionDigits: 2 })

// ── TrendChart — 막대(1~2계열) + 라인(1계열) 콤보. 월 클릭 → onSelect(month) ──
export interface TrendSeries {
  key: string
  label: string
  values: number[]
  color: string // tailwind 색이 아닌 실제 css 색상값
  kind: 'bar' | 'line'
}

export function TrendChart({
  labels,
  series,
  height = 180,
  onSelect,
  formatValue = nf,
}: {
  labels: string[]
  series: TrendSeries[]
  height?: number
  onSelect?: (label: string) => void
  formatValue?: (n: number) => string
}) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 720
  const H = height
  const padL = 8
  const padB = 18
  const padT = 14
  const innerW = W - padL * 2
  const innerH = H - padB - padT
  const n = labels.length
  const max = useMemo(
    () => Math.max(1, ...series.flatMap((s) => s.values.map((v) => Math.abs(v)))),
    [series],
  )
  const slot = innerW / Math.max(1, n)
  const bars = series.filter((s) => s.kind === 'bar')
  const lines = series.filter((s) => s.kind === 'line')
  const barW = Math.min(18, (slot * 0.6) / Math.max(1, bars.length))

  const y = (v: number) => padT + innerH - (Math.abs(v) / max) * innerH

  return (
    <div className="relative w-full">
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img">
        {/* 기준선 */}
        {[0.5, 1].map((f) => (
          <line
            key={f}
            x1={padL}
            x2={W - padL}
            y1={padT + innerH * (1 - f)}
            y2={padT + innerH * (1 - f)}
            className="stroke-current text-slatey/20"
            strokeDasharray="3 4"
          />
        ))}
        {/* 막대 */}
        {labels.map((lb, i) => (
          <g key={lb}>
            {bars.map((s, bi) => {
              const v = s.values[i] ?? 0
              const x = padL + slot * i + slot / 2 - (barW * bars.length) / 2 + bi * barW
              return (
                <rect
                  key={s.key}
                  x={x}
                  y={y(v)}
                  width={Math.max(2, barW - 2)}
                  height={Math.max(0, padT + innerH - y(v))}
                  rx={2}
                  fill={s.color}
                  opacity={hover === null || hover === i ? 0.9 : 0.35}
                />
              )
            })}
            {/* 히트영역 + 라벨(격월 표시) */}
            <rect
              x={padL + slot * i}
              y={0}
              width={slot}
              height={H}
              fill="transparent"
              className={onSelect ? 'cursor-pointer' : ''}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onSelect?.(lb)}
            />
            {(n <= 8 || i % 2 === (n - 1) % 2) && (
              <text
                x={padL + slot * i + slot / 2}
                y={H - 4}
                textAnchor="middle"
                className="fill-current text-slatey"
                fontSize={10}
              >
                {lb.slice(2).replace('-', '.')}
              </text>
            )}
          </g>
        ))}
        {/* 라인 */}
        {lines.map((s) => {
          const pts = s.values
            .map((v, i) => `${padL + slot * i + slot / 2},${y(v ?? 0)}`)
            .join(' ')
          return (
            <g key={s.key}>
              <polyline points={pts} fill="none" stroke={s.color} strokeWidth={2} />
              {s.values.map((v, i) => (
                <circle
                  key={i}
                  cx={padL + slot * i + slot / 2}
                  cy={y(v ?? 0)}
                  r={hover === i ? 4 : 2.5}
                  fill={s.color}
                />
              ))}
            </g>
          )
        })}
      </svg>
      {/* 호버 툴팁 */}
      {hover !== null && (
        <div className="pointer-events-none absolute top-0 left-1/2 z-10 -translate-x-1/2 rounded-lg border border-hairline bg-graphite px-2.5 py-1.5 text-[11px] text-bone shadow-lg">
          <b>{labels[hover]}</b>
          {series.map((s) => (
            <div key={s.key} className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-sm" style={{ background: s.color }} />
              {s.label}: {formatValue(s.values[hover] ?? 0)}
            </div>
          ))}
        </div>
      )}
      {/* 범례 */}
      <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-slatey">
        {series.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span
              className={`inline-block ${s.kind === 'line' ? 'h-0.5 w-4' : 'h-2.5 w-2.5 rounded-sm'}`}
              style={{ background: s.color }}
            />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Donut — 분포(상태·보유/매각). 조각 클릭 → onSelect(key) ──
export interface DonutSlice {
  key: string
  label: string
  value: number
  color: string
}

export function Donut({
  slices,
  size = 120,
  onSelect,
}: {
  slices: DonutSlice[]
  size?: number
  onSelect?: (key: string) => void
}) {
  const total = Math.max(
    1e-9,
    slices.reduce((a, s) => a + Math.max(0, s.value), 0),
  )
  const R = 45
  const C = 2 * Math.PI * R
  let acc = 0
  return (
    <div className="flex items-center gap-3">
      <svg viewBox="0 0 120 120" width={size} height={size} className="shrink-0 -rotate-90">
        {slices.map((s) => {
          const frac = Math.max(0, s.value) / total
          const dash = `${frac * C} ${C}`
          const offset = -acc * C
          acc += frac
          return (
            <circle
              key={s.key}
              cx={60}
              cy={60}
              r={R}
              fill="none"
              stroke={s.color}
              strokeWidth={16}
              strokeDasharray={dash}
              strokeDashoffset={offset}
              className={onSelect ? 'cursor-pointer' : ''}
              onClick={() => onSelect?.(s.key)}
            />
          )
        })}
      </svg>
      <ul className="space-y-1 text-xs">
        {slices.map((s) => (
          <li key={s.key}>
            <button
              type="button"
              onClick={() => onSelect?.(s.key)}
              className={`flex items-center gap-1.5 ${onSelect ? 'hover:underline' : 'cursor-default'} text-ash`}
            >
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />
              {s.label}
              <span className="font-mono tabular-nums text-bone">{nf(s.value)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ── MiniBars — 소형 수평 막대(지역 상위 등). 행 클릭 → onSelect(key) ──
export function MiniBars({
  items,
  onSelect,
  valueLabel = (v: number) => nf(v),
}: {
  items: { key: string; label: string; value: number; sub?: string }[]
  onSelect?: (key: string) => void
  valueLabel?: (v: number) => string
}) {
  const max = Math.max(1, ...items.map((i) => i.value))
  return (
    <ul className="space-y-1.5">
      {items.map((it) => (
        <li key={it.key}>
          <button
            type="button"
            onClick={() => onSelect?.(it.key)}
            className={`block w-full text-left ${onSelect ? 'group' : 'cursor-default'}`}
          >
            <div className="mb-0.5 flex items-baseline justify-between text-xs">
              <span className="text-ash group-hover:text-bone">{it.label}</span>
              <span className="font-mono tabular-nums text-bone">
                {valueLabel(it.value)}
                {it.sub && <span className="ml-1 text-[10px] text-slatey">{it.sub}</span>}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-elevate">
              <div
                className="h-full rounded-full bg-emerald-500/80"
                style={{ width: `${(it.value / max) * 100}%` }}
              />
            </div>
          </button>
        </li>
      ))}
    </ul>
  )
}
