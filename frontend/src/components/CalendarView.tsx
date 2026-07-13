// 월간/주간 캘린더 (플랜 §4.2 / SCR-11) — 자체 구현, 순수 Date (라이브러리 금지)
import { fmtTime } from '../lib/format'

export interface CalendarEventItem<T> {
  id: string
  start: Date
  title: string
  /** 담당자 색상 도트 클래스 */
  dotClass: string
  /** 완료·취소 등 톤 다운 */
  muted?: boolean
  data: T
}

interface CalendarViewProps<T> {
  mode: 'month' | 'week'
  /** 표시 기준일 (해당 월/주) */
  cursor: Date
  events: CalendarEventItem<T>[]
  onEventClick?: (data: T) => void
  /** 빈 영역 클릭 → 해당 일자로 일정 등록 */
  onDayClick?: (date: Date) => void
}

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']

function sameDate(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

/** 해당 주의 일요일 */
function weekStart(d: Date): Date {
  const s = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  s.setDate(s.getDate() - s.getDay())
  return s
}

export function CalendarView<T>({
  mode,
  cursor,
  events,
  onEventClick,
  onDayClick,
}: CalendarViewProps<T>) {
  const today = new Date()

  // 표시할 날짜 배열 계산
  const days: Date[] = []
  if (mode === 'month') {
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1)
    const start = weekStart(first)
    const last = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0)
    // 말일이 포함된 주까지
    const totalDays = Math.ceil((last.getDate() + first.getDay()) / 7) * 7
    for (let i = 0; i < totalDays; i++) {
      const d = new Date(start)
      d.setDate(start.getDate() + i)
      days.push(d)
    }
  } else {
    const start = weekStart(cursor)
    for (let i = 0; i < 7; i++) {
      const d = new Date(start)
      d.setDate(start.getDate() + i)
      days.push(d)
    }
  }

  const eventsOf = (d: Date) =>
    events
      .filter((e) => sameDate(e.start, d))
      .sort((a, b) => a.start.getTime() - b.start.getTime())

  const dayHeaderColor = (idx: number) =>
    idx % 7 === 0 ? 'text-rose-400' : idx % 7 === 6 ? 'text-blue-400' : 'text-ash'

  return (
    <div className="overflow-hidden rounded-3xl border border-hairline bg-graphite">
      {/* 요일 헤더 */}
      <div className="grid grid-cols-7 border-b border-hairline bg-elevate">
        {WEEKDAYS.map((w, i) => (
          <div
            key={w}
            className={`py-2 text-center text-xs font-semibold ${dayHeaderColor(i)}`}
          >
            {w}
          </div>
        ))}
      </div>

      {/* 날짜 그리드 */}
      <div className="grid grid-cols-7">
        {days.map((d, idx) => {
          const inMonth = mode === 'week' || d.getMonth() === cursor.getMonth()
          const isToday = sameDate(d, today)
          const dayEvents = eventsOf(d)
          const maxShow = mode === 'month' ? 3 : dayEvents.length
          return (
            <div
              key={idx}
              onClick={onDayClick ? () => onDayClick(d) : undefined}
              className={`border-b border-hairline p-1.5 align-top ${
                idx % 7 !== 6 ? 'border-r' : ''
              } ${mode === 'month' ? 'min-h-[92px]' : 'min-h-[200px]'} ${
                inMonth ? 'bg-graphite' : 'bg-elevate'
              } ${onDayClick ? 'cursor-pointer hover:bg-elevate' : ''}`}
            >
              <span
                className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs ${
                  isToday
                    ? 'bg-primary font-bold text-on-primary'
                    : inMonth
                      ? 'font-medium text-bone'
                      : 'text-slatey'
                }`}
              >
                {d.getDate()}
              </span>
              <div className="mt-1 space-y-1">
                {dayEvents.slice(0, maxShow).map((event) => (
                  <button
                    key={event.id}
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      onEventClick?.(event.data)
                    }}
                    className={`flex w-full items-center gap-1 truncate rounded px-1 py-0.5 text-left text-[11px] hover:bg-elevate ${
                      event.muted ? 'text-slatey line-through' : 'text-bone'
                    }`}
                    title={event.title}
                  >
                    <span
                      className={`h-1.5 w-1.5 shrink-0 rounded-full ${event.dotClass}`}
                      aria-hidden="true"
                    />
                    {mode === 'week' && (
                      <span className="shrink-0 font-mono text-[10px] text-slatey">
                        {fmtTime(event.start)}
                      </span>
                    )}
                    <span className="truncate">{event.title}</span>
                  </button>
                ))}
                {dayEvents.length > maxShow && (
                  <p className="px-1 text-[10px] text-slatey">
                    +{dayEvents.length - maxShow}건 더보기
                  </p>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
