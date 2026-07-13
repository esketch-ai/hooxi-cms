import { CaretLeft, CaretRight } from '@phosphor-icons/react'

interface PaginationProps {
  total: number
  page: number // 1-based
  pageSize: number
  onChange: (page: number) => void
  className?: string
}

export function Pagination({
  total,
  page,
  pageSize,
  onChange,
  className = '',
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)

  // 현재 페이지 주변 최대 5개 노출
  const start = Math.max(1, Math.min(page - 2, totalPages - 4))
  const pages = Array.from(
    { length: Math.min(5, totalPages) },
    (_, i) => start + i,
  )

  return (
    <div
      className={`flex flex-col items-center justify-between gap-3 sm:flex-row ${className}`}
    >
      <p className="text-sm text-ash">
        총 {total.toLocaleString()}건 중 {from}~{to} 표시
      </p>
      <nav className="flex items-center gap-1" aria-label="페이지 이동">
        <button
          type="button"
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
          className="flex h-8 w-8 items-center justify-center rounded-md border border-hairline bg-graphite text-smoke hover:bg-white/5 disabled:opacity-40"
          aria-label="이전 페이지"
        >
          <CaretLeft size={14} />
        </button>
        {pages.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => onChange(p)}
            aria-current={p === page ? 'page' : undefined}
            className={`h-8 min-w-8 rounded-md border px-2 text-sm ${
              p === page
                ? 'border-snow bg-snow font-semibold text-graphite'
                : 'border-hairline bg-graphite text-ash hover:bg-white/5'
            }`}
          >
            {p}
          </button>
        ))}
        <button
          type="button"
          onClick={() => onChange(page + 1)}
          disabled={page >= totalPages}
          className="flex h-8 w-8 items-center justify-center rounded-md border border-hairline bg-graphite text-smoke hover:bg-white/5 disabled:opacity-40"
          aria-label="다음 페이지"
        >
          <CaretRight size={14} />
        </button>
      </nav>
    </div>
  )
}
