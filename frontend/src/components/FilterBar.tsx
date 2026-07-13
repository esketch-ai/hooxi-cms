// 목록 필터 표준 (플랜 §4.2): select 3개 + 검색 input
import type { ChangeEvent, ReactNode } from 'react'
import { MagnifyingGlass } from '@phosphor-icons/react'

export interface FilterOption {
  value: string
  label: string
}

interface FilterSelectProps {
  label: string
  value: string
  options: FilterOption[]
  /** 첫 옵션(전체) 라벨 — 기본 '전체' */
  allLabel?: string
  onChange: (value: string) => void
  className?: string
}

export function FilterSelect({
  label,
  value,
  options,
  allLabel = '전체',
  onChange,
  className = '',
}: FilterSelectProps) {
  return (
    <label className={`flex items-center gap-1.5 ${className}`}>
      <span className="shrink-0 text-xs font-medium text-ash">{label}</span>
      <select
        value={value}
        onChange={(e: ChangeEvent<HTMLSelectElement>) => onChange(e.target.value)}
        className="h-9 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
      >
        <option value="">{allLabel}</option>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  )
}

interface FilterSearchProps {
  value: string
  placeholder?: string
  onChange: (value: string) => void
  className?: string
}

export function FilterSearch({
  value,
  placeholder = '검색',
  onChange,
  className = '',
}: FilterSearchProps) {
  return (
    <div className={`relative ${className}`}>
      <MagnifyingGlass
        size={15}
        className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-smoke"
      />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-9 w-full rounded-lg border border-hairline bg-graphite pr-3 pl-8 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
        aria-label={placeholder}
      />
    </div>
  )
}

interface FilterBarProps {
  children: ReactNode
  className?: string
}

export function FilterBar({ children, className = '' }: FilterBarProps) {
  return (
    <div
      className={`flex flex-wrap items-center gap-2.5 rounded-3xl border border-hairline bg-graphite px-3.5 py-2.5 ${className}`}
    >
      {children}
    </div>
  )
}
