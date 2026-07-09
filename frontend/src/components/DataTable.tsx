// 데스크톱 테이블 ↔ 모바일 카드 자동 전환 (플랜 §4.2 DataTable+CardList / §7 디바이스 전략)
import type { ReactNode } from 'react'
import { EmptyState } from './EmptyState'
import { SkeletonCards, SkeletonTableRows } from './Skeleton'

export interface Column<T> {
  key: string
  header: ReactNode
  /** th/td 공통 클래스 (정렬·너비) */
  className?: string
  /** 모바일 카드 전환 시 숨김이 아닌, 테이블 셀 렌더러 */
  render: (row: T) => ReactNode
}

interface DataTableProps<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  /** 모바일(<sm) 카드 렌더러 — 미지정 시 모바일에서도 테이블(가로 스크롤) */
  renderCard?: (row: T) => ReactNode
  onRowClick?: (row: T) => void
  /** 행 톤 다운 등 조건부 클래스 (예: HOLD 고객사) */
  rowClassName?: (row: T) => string
  isLoading?: boolean
  emptyTitle?: string
  emptyDescription?: string
  emptyAction?: ReactNode
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  renderCard,
  onRowClick,
  rowClassName,
  isLoading = false,
  emptyTitle = '데이터가 없습니다',
  emptyDescription,
  emptyAction,
}: DataTableProps<T>) {
  if (isLoading) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="hidden sm:block">
          <SkeletonTableRows rows={5} />
        </div>
        <div className="sm:hidden">
          <SkeletonCards count={3} />
        </div>
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} />
    )
  }

  return (
    <>
      {/* 데스크톱·태블릿: 테이블 */}
      <div
        className={`overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm ${
          renderCard ? 'hidden sm:block' : ''
        }`}
      >
        <table className="w-full min-w-max text-left text-sm">
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50/60">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={`px-4 py-3 text-xs font-semibold tracking-wide text-slate-500 ${col.className ?? ''}`}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={`border-b border-slate-50 last:border-b-0 ${
                  onRowClick ? 'cursor-pointer hover:bg-slate-50/70' : ''
                } ${rowClassName?.(row) ?? ''}`}
              >
                {columns.map((col) => (
                  <td key={col.key} className={`px-4 py-3 align-middle ${col.className ?? ''}`}>
                    {col.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 모바일: 카드 리스트 */}
      {renderCard && (
        <div className="space-y-3 sm:hidden">
          {rows.map((row) => (
            <div
              key={rowKey(row)}
              className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm ${rowClassName?.(row) ?? ''}`}
            >
              {renderCard(row)}
            </div>
          ))}
        </div>
      )}
    </>
  )
}
