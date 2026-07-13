// 팀 공용 칸반 (플랜 §4.2 / SCR-02) — PC: HTML5 드래그앤드롭 / 모바일: 탭 전환
import { useState, type DragEvent, type ReactNode } from 'react'
import { CaretDown, CaretRight } from '@phosphor-icons/react'

export interface KanbanColumn {
  key: string
  title: string
  /** 컬럼 헤더 도트 색 */
  dotClass?: string
  /** 기본 접힘 컬럼 (완료 등) */
  collapsible?: boolean
}

interface KanbanBoardProps<T> {
  columns: KanbanColumn[]
  items: T[]
  itemKey: (item: T) => string
  columnOf: (item: T) => string
  renderCard: (item: T) => ReactNode
  /** 드래그앤드롭 상태 변경 (PC) */
  onMove?: (itemId: string, toColumn: string) => void
  onCardClick?: (item: T) => void
}

export function KanbanBoard<T>({
  columns,
  items,
  itemKey,
  columnOf,
  renderCard,
  onMove,
  onCardClick,
}: KanbanBoardProps<T>) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(columns.filter((c) => c.collapsible).map((c) => [c.key, true])),
  )
  const [dragOverCol, setDragOverCol] = useState<string | null>(null)
  // 모바일 탭 전환 — 첫 컬럼 기본
  const [activeTab, setActiveTab] = useState(columns[0]?.key ?? '')

  const byColumn = (key: string) => items.filter((item) => columnOf(item) === key)

  const handleDrop = (e: DragEvent<HTMLDivElement>, colKey: string) => {
    e.preventDefault()
    setDragOverCol(null)
    const id = e.dataTransfer.getData('text/plain')
    if (id && onMove) onMove(id, colKey)
  }

  const renderColumnBody = (col: KanbanColumn) => {
    const colItems = byColumn(col.key)
    return (
      <div className="space-y-2.5">
        {colItems.length === 0 && (
          <p className="rounded-lg border border-dashed border-hairline py-6 text-center text-xs text-slatey">
            카드 없음
          </p>
        )}
        {colItems.map((item) => (
          <div
            key={itemKey(item)}
            draggable={!!onMove}
            onDragStart={(e) => e.dataTransfer.setData('text/plain', itemKey(item))}
            onClick={onCardClick ? () => onCardClick(item) : undefined}
            className={onCardClick ? 'cursor-pointer' : ''}
          >
            {renderCard(item)}
          </div>
        ))}
      </div>
    )
  }

  return (
    <>
      {/* 모바일·태블릿(<lg): 탭 전환 */}
      <div className="lg:hidden">
        <div className="mb-3 flex gap-1.5 overflow-x-auto">
          {columns.map((col) => (
            <button
              key={col.key}
              type="button"
              onClick={() => setActiveTab(col.key)}
              className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium ${
                activeTab === col.key
                  ? 'border-snow bg-primary text-on-primary'
                  : 'border-hairline bg-graphite text-ash'
              }`}
            >
              <span className={`h-2 w-2 rounded-full ${col.dotClass ?? 'bg-white/40'}`} />
              {col.title}
              <span className="font-semibold">{byColumn(col.key).length}</span>
            </button>
          ))}
        </div>
        {columns
          .filter((col) => col.key === activeTab)
          .map((col) => (
            <div key={col.key}>{renderColumnBody(col)}</div>
          ))}
      </div>

      {/* 데스크톱(lg+): 4컬럼 보드 + 드래그앤드롭 */}
      <div className="hidden gap-4 lg:flex lg:items-start">
        {columns.map((col) => {
          const isCollapsed = collapsed[col.key]
          const colItems = byColumn(col.key)
          if (isCollapsed) {
            return (
              <button
                key={col.key}
                type="button"
                onClick={() => setCollapsed((prev) => ({ ...prev, [col.key]: false }))}
                className="flex w-12 shrink-0 flex-col items-center gap-2 rounded-3xl border border-hairline bg-graphite py-4 text-smoke hover:bg-elevate"
                title={`${col.title} 펼치기`}
              >
                <CaretRight size={14} />
                <span className="text-xs font-semibold whitespace-nowrap [writing-mode:vertical-lr]">
                  {col.title} {colItems.length}
                </span>
              </button>
            )
          }
          return (
            <div
              key={col.key}
              onDragOver={(e) => {
                if (!onMove) return
                e.preventDefault()
                setDragOverCol(col.key)
              }}
              onDragLeave={() => setDragOverCol((prev) => (prev === col.key ? null : prev))}
              onDrop={(e) => handleDrop(e, col.key)}
              className={`min-w-0 flex-1 rounded-3xl border p-3 transition-colors ${
                dragOverCol === col.key
                  ? 'border-white/30 bg-elevate-strong'
                  : 'border-hairline bg-graphite'
              }`}
            >
              <div className="mb-3 flex items-center gap-2 px-1">
                <span className={`h-2.5 w-2.5 rounded-full ${col.dotClass ?? 'bg-white/40'}`} />
                <h3 className="text-sm font-semibold text-bone">{col.title}</h3>
                <span className="rounded-full bg-elevate-strong px-2 py-0.5 text-xs font-semibold text-ash">
                  {colItems.length}
                </span>
                {col.collapsible && (
                  <button
                    type="button"
                    onClick={() => setCollapsed((prev) => ({ ...prev, [col.key]: true }))}
                    className="ml-auto rounded p-0.5 text-smoke hover:bg-elevate"
                    aria-label={`${col.title} 접기`}
                  >
                    <CaretDown size={14} />
                  </button>
                )}
              </div>
              {renderColumnBody(col)}
            </div>
          )
        })}
      </div>
    </>
  )
}
