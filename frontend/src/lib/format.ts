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

// ── 서버 생성 시각(naive UTC) 전용 파서/포맷터 ─────────────────────────
// 백엔드 utcnow()는 tz 정보 없는 UTC 문자열('Z' 없음)을 내려보낸다.
// created_at·updated_at·last_message_at·requested_at·approved_at·sent_at·
// billed_at·completed_at·confirmed_at 등 서버 기록 시각에만 사용할 것.
// (activity_date·due_date·일정 시각 등 사용자 입력 벽시계는 fmtDate/fmtDateTime 유지)

/** 서버 생성 시각(naive UTC) 파싱 — 타임존 정보 없으면 UTC로 간주 */
export function parseServerUtc(iso: string): Date {
  return new Date(/Z|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso + 'Z')
}

function toServerDate(value?: string | Date | null): Date | null {
  if (value === null || value === undefined || value === '') return null
  const d = value instanceof Date ? value : parseServerUtc(value)
  return Number.isNaN(d.getTime()) ? null : d
}

/** 서버 시각 → 'YYYY-MM-DD' (로컬 시간대 기준) */
export function fmtServerDate(value?: string | Date | null): string {
  const d = toServerDate(value)
  return d ? fmtDate(d) : value ? String(value) : '—'
}

/** 서버 시각 → 'MM-DD HH:mm' (로컬 시간대 기준) */
export function fmtServerDateTime(value?: string | Date | null): string {
  const d = toServerDate(value)
  return d ? fmtDateTime(d) : value ? String(value) : '—'
}

/** 서버 시각 → 'HH:mm' (로컬 시간대 기준) */
export function fmtServerTime(value?: string | Date | null): string {
  const d = toServerDate(value)
  return d ? fmtTime(d) : ''
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

/** 서버 시각 기준 경과 시간 — elapsed()의 서버 생성 시각(naive UTC) 버전 */
export function elapsedServer(value?: string | null): string {
  if (!value) return ''
  const d = parseServerUtc(value)
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
