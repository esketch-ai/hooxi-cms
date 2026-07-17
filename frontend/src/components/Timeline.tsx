// 활동 타임라인 (플랜 §4.2) — 도트 색상 + 고객사/배지/경과/내용, SCR-01·03D 공용
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Paperclip } from '@phosphor-icons/react'
import type { ActivityHistory, Document } from '../types'
import { StatusBadge } from './StatusBadge'
import { AuditLine } from './AuditLine'
import { DocumentPreviewModal } from './DocumentPreviewModal'
import { previewKind } from '../lib/download'
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
  /** history_id → 현장 첨부(사진·서명) — 전달 시 클립 개수·서명 배지 + 미리보기 (SCR-03D) */
  documentsByHistory?: Record<string, Document[]>
  className?: string
}

export function Timeline({
  items,
  showClient = true,
  documentsByHistory,
  className = '',
}: TimelineProps) {
  // 첨부 제목 클릭 → 미리보기(이미지/PDF만) — 다운로드는 보고서·문서 탭에서
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null)

  return (
    <>
      <ol className={`relative space-y-5 border-l border-hairline pl-5 ${className}`}>
        {items.map((item) => {
          const docs = documentsByHistory?.[item.history_id] ?? []
          return (
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
                {docs.length > 0 && (
                  <span
                    className="inline-flex items-center gap-0.5 rounded-full border border-hairline bg-elevate-strong px-1.5 py-0.5 text-[10px] font-medium text-ash"
                    title={`현장 첨부 ${docs.length}건`}
                  >
                    <Paperclip size={11} />
                    {docs.length}
                  </span>
                )}
                {docs.some((d) => d.doc_type === 'SIGN') && (
                  <span className="inline-flex rounded bg-elevate-strong px-1 py-0.5 text-[10px] font-medium text-ash">
                    서명
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm font-medium text-bone">{item.title}</p>
              {item.content && (
                <p className="mt-0.5 line-clamp-2 text-sm text-ash">{item.content}</p>
              )}
              {docs.length > 0 && (
                <ul className="mt-1 flex flex-wrap gap-1.5">
                  {docs.map((d) =>
                    previewKind(d) ? (
                      <li key={d.doc_id}>
                        <button
                          type="button"
                          onClick={() => setPreviewDoc(d)}
                          className="max-w-48 truncate rounded-full border border-hairline px-2 py-0.5 text-xs text-bone hover:bg-elevate"
                          title="미리보기"
                        >
                          {d.title}
                        </button>
                      </li>
                    ) : (
                      <li
                        key={d.doc_id}
                        className="max-w-48 truncate rounded-full border border-hairline px-2 py-0.5 text-xs text-ash"
                      >
                        {d.title}
                      </li>
                    ),
                  )}
                </ul>
              )}
              <AuditLine
                createdByName={item.created_by_name ?? item.manager_name}
                createdAt={item.created_at}
                auto={!!item.is_auto}
                className="mt-1"
              />
            </li>
          )
        })}
      </ol>
      <DocumentPreviewModal doc={previewDoc} onClose={() => setPreviewDoc(null)} />
    </>
  )
}
