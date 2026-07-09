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
  const base = 'rounded-xl p-5 shadow-sm border'
  const variants: Record<NonNullable<KpiCardProps['variant']>, string> = {
    default: 'bg-white border-slate-200',
    // danger: 좌측 빨간 바 (플랜 §4.2)
    danger: 'bg-white border-slate-200 border-l-4 border-l-rose-500',
    // dark: 민감(금액) variant
    dark: 'bg-slate-800 border-slate-800 text-white',
  }
  const titleColor = variant === 'dark' ? 'text-slate-300' : 'text-slate-500'
  const subColor = variant === 'dark' ? 'text-slate-400' : 'text-slate-400'

  return (
    <div className={`${base} ${variants[variant]} ${className}`}>
      <div className="flex items-start justify-between">
        <p className={`text-sm font-medium ${titleColor}`}>{title}</p>
        {icon && (
          <span className={variant === 'dark' ? 'text-slate-400' : 'text-slate-400'}>
            {icon}
          </span>
        )}
      </div>
      <div className="mt-2 text-2xl font-bold tracking-tight">{value}</div>
      {sub && <div className={`mt-1 text-xs ${subColor}`}>{sub}</div>}
    </div>
  )
}
