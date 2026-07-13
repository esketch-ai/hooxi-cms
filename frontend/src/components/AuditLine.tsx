// 공동 관리 가시화 (01_COMMON §4): "작성 홍길동 · 07-08 14:00 / 수정 …"
// 자동 생성 레코드는 [자동] 태그로 수기 기록과 구분

interface AuditLineProps {
  createdByName?: string | null
  createdAt?: string | null
  updatedByName?: string | null
  updatedAt?: string | null
  /** 자동 생성 레코드(보고서 발송·일정 완료 적재 등) */
  auto?: boolean
  className?: string
}

import { parseServerUtc } from '../lib/format'

function formatDateTime(value?: string | null): string {
  if (!value) return ''
  // 작성/수정 시각은 서버 생성 시각(naive UTC) — UTC로 파싱해 로컬(KST)로 표시
  const d = parseServerUtc(value)
  if (Number.isNaN(d.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function AuditLine({
  createdByName,
  createdAt,
  updatedByName,
  updatedAt,
  auto = false,
  className = '',
}: AuditLineProps) {
  const parts: string[] = []
  if (createdByName || createdAt) {
    parts.push(
      `작성 ${createdByName ?? '알 수 없음'}${createdAt ? ` · ${formatDateTime(createdAt)}` : ''}`,
    )
  }
  if (updatedByName || updatedAt) {
    parts.push(
      `수정 ${updatedByName ?? '알 수 없음'}${updatedAt ? ` · ${formatDateTime(updatedAt)}` : ''}`,
    )
  }

  if (parts.length === 0 && !auto) return null

  return (
    <p className={`text-xs text-slatey ${className}`}>
      {auto && (
        <span className="mr-1.5 inline-flex items-center rounded bg-white/10 px-1 py-0.5 text-[10px] font-medium text-ash">
          자동
        </span>
      )}
      {parts.join(' / ')}
    </p>
  )
}
