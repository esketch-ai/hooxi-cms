import type { ReactNode } from 'react'

interface KpiCardProps {
  title: string
  value: ReactNode
  sub?: ReactNode
  icon?: ReactNode
  variant?: 'default' | 'danger' | 'dark'
  className?: string
}

export function KpiCard({
  title,
  value,
  sub,
  icon,
  variant = 'default',
  className = '',
}: KpiCardProps) {
  const base = 'rounded-3xl p-5 border'
  const variants: Record<NonNullable<KpiCardProps['variant']>, string> = {
    default: 'bg-graphite border-hairline',
    // danger: 값 색으로만 강조 (좌측 컬러 바는 제거 — 기본 테마 인상 방지)
    danger: 'bg-graphite border-hairline',
    // dark: 민감(금액) variant
    dark: 'bg-graphite-2 border-hairline text-bone',
  }
  const valueColor = variant === 'danger' ? 'text-rose-600 dark:text-rose-300' : ''
  const titleColor = variant === 'dark' ? 'text-ash' : 'text-ash'
  const subColor = variant === 'dark' ? 'text-slatey' : 'text-slatey'

  return (
    <div className={`${base} ${variants[variant]} ${className}`}>
      <div className="flex items-start justify-between">
        <p className={`text-sm font-medium ${titleColor}`}>{title}</p>
        {icon && (
          <span className={variant === 'dark' ? 'text-slatey' : 'text-slatey'}>
            {icon}
          </span>
        )}
      </div>
      <div className={`mt-2 text-2xl font-bold tracking-tight ${valueColor}`}>{value}</div>
      {sub && <div className={`mt-1 text-xs ${subColor}`}>{sub}</div>}
    </div>
  )
}
