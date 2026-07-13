import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
  className?: string
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className = '',
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center rounded-3xl border border-dashed border-hairline bg-graphite px-6 py-16 text-center ${className}`}
    >
      {icon && <div className="mb-3 text-slatey">{icon}</div>}
      <p className="text-sm font-semibold text-bone">{title}</p>
      {description && (
        <p className="mt-1 max-w-sm text-sm text-slatey">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
