// 활동 타임라인 (플랜 §4.2) — 도트 색상 + 고객사/배지/경과/내용, SCR-01·03D 공용
import { Link } from 'react-router-dom'
import type { ActivityHistory } from '../types'
import { StatusBadge } from './StatusBadge'
import { AuditLine } from './AuditLine'
import { fmtDateTime } from '../lib/format'

// 활동 유형 → 도트 색 (§3.3 활동 유형 배지 색과 동일 계열)
const DOT_COLORS: Record<string, string> = {
  CALL: 'bg-emerald-500',
  MEETING: 'bg-blue-500',
  SITE_VISIT: 'bg-purple-500',
  EMAIL: 'bg-white/40',
  ISSUE: 'bg-rose-500',
  KAKAO: 'bg-amber-400',
}

interface TimelineProps {
  items: ActivityHistory[]
  /** 고객사명 표기 여부 (고객사 상세에서는 생략) */
  showClient?: boolean
  className?: string
}

export function Timeline({ items, showClient = true, className = '' }: TimelineProps) {
  return (
    <ol className={`relative space-y-5 border-l border-hairline pl-5 ${className}`}>
      {items.map((item) => (
        <li key={item.history_id} className="relative">
          <span
            className={`absolute top-1.5 -left-[26.5px] h-3 w-3 rounded-full border-2 border-graphite ${
              DOT_COLORS[item.activity_type] ?? 'bg-white/40'
            }`}
            aria-hidden="true"
          />
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge domain="activity" value={item.activity_type} />
            {item.activity_type === 'ISSUE' && item.issue_status && (
              <StatusBadge domain="issue" value={item.issue_status} />
            )}
            {showClient &&
              (item.client_id ? (
                <Link
                  to={`/clients/${item.client_id}`}
                  className="text-sm font-semibold text-bone hover:underline"
                >
                  {item.client_name ?? '고객사'}
                </Link>
              ) : (
                <span className="text-sm text-slatey">미지정 고객</span>
              ))}
            <span className="text-xs text-slatey">{fmtDateTime(item.activity_date)}</span>
          </div>
          <p className="mt-1 text-sm font-medium text-bone">{item.title}</p>
          {item.content && (
            <p className="mt-0.5 line-clamp-2 text-sm text-ash">{item.content}</p>
          )}
          <AuditLine
            createdByName={item.created_by_name ?? item.manager_name}
            createdAt={item.created_at}
            auto={!!item.is_auto}
            className="mt-1"
          />
        </li>
      ))}
    </ol>
  )
}
