import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

interface KpiCardProps {
  title: string
  value: ReactNode
  sub?: ReactNode
  icon?: ReactNode
  variant?: 'default' | 'danger' | 'dark'
  /** 지정 시 카드 전체가 해당 화면으로 가는 링크가 된다 (막다른 정보 방지) */
  to?: string
  /** 밀도 축소 — 액션 센터 등 다른 주인공이 있는 화면에서 KPI 위계를 낮출 때 */
  compact?: boolean
  className?: string
}

export function KpiCard({
  title,
  value,
  sub,
  icon,
  variant = 'default',
  to,
  compact = false,
  className = '',
}: KpiCardProps) {
  const base = `rounded-3xl border ${compact ? 'p-4' : 'p-5'}`
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

  const content = (
    <>
      <div className="flex items-start justify-between">
        <p className={`text-sm font-medium ${titleColor}`}>{title}</p>
        {icon && (
          <span className={variant === 'dark' ? 'text-slatey' : 'text-slatey'}>
            {icon}
          </span>
        )}
      </div>
      <div
        className={`font-bold tracking-tight ${compact ? 'mt-1.5 text-xl' : 'mt-2 text-2xl'} ${valueColor}`}
      >
        {value}
      </div>
      {sub && <div className={`mt-1 text-xs ${subColor}`}>{sub}</div>}
    </>
  )

  // to가 있으면 Link 래핑 — hover 표면 반응으로 클릭 가능함을 드러낸다
  if (to) {
    return (
      <Link
        to={to}
        className={`block cursor-pointer transition-colors hover:bg-elevate ${base} ${variants[variant]} ${className}`}
      >
        {content}
      </Link>
    )
  }

  return <div className={`${base} ${variants[variant]} ${className}`}>{content}</div>
}
