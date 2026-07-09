// 날짜·금액 포맷 유틸 — 순수 Date 기반 (외부 라이브러리 금지)

const pad = (n: number) => String(n).padStart(2, '0')

/** 'YYYY-MM-DD' */
export function fmtDate(value?: string | Date | null): string {
  if (!value) return '—'
  const d = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** 'MM-DD HH:mm' */
export function fmtDateTime(value?: string | Date | null): string {
  if (!value) return '—'
  const d = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 'HH:mm' */
export function fmtTime(value?: string | Date | null): string {
  if (!value) return ''
  const d = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 'YYYY-MM' */
export function fmtMonth(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`
}

/** datetime-local input용 'YYYY-MM-DDTHH:mm' */
export function toDatetimeLocal(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 접수 경과 시간: '방금 전' / 'N분 경과' / 'N시간 경과' / 'N일 경과' */
export function elapsed(value?: string | null): string {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  const diffMs = Date.now() - d.getTime()
  const mins = Math.floor(diffMs / 60_000)
  if (mins < 1) return '방금 전'
  if (mins < 60) return `${mins}분 경과`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}시간 경과`
  const days = Math.floor(hours / 24)
  return `${days}일 경과`
}

/** D-day 계산: due 기준. { label: 'D-3'|'D-DAY'|'D+2', overdue } */
export function dday(due?: string | null): { label: string; overdue: boolean; imminent: boolean } | null {
  if (!due) return null
  const d = new Date(due)
  if (Number.isNaN(d.getTime())) return null
  const today = new Date()
  const a = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const b = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const diff = Math.round((b.getTime() - a.getTime()) / 86_400_000)
  if (diff === 0) return { label: 'D-DAY', overdue: false, imminent: true }
  if (diff > 0) return { label: `D-${diff}`, overdue: false, imminent: diff <= 3 }
  return { label: `D+${-diff}`, overdue: true, imminent: true }
}

/** '₩ 12,345,678' */
export function fmtMoney(value?: number | string | null): string {
  if (value === null || value === undefined || value === '') return '미정'
  const n = typeof value === 'string' ? Number(value) : value
  if (Number.isNaN(n)) return String(value)
  return `₩ ${n.toLocaleString('ko-KR')}`
}

/** '12.5 %' */
export function fmtRate(value?: number | string | null): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'string' ? Number(value) : value
  if (Number.isNaN(n)) return String(value)
  return `${n} %`
}

/** 전화번호 → tel: 링크 href */
export function telHref(phone?: string | null): string {
  return `tel:${(phone ?? '').replace(/[^0-9+]/g, '')}`
}
