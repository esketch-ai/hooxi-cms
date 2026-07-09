// SCR-08 승인 대기 큐 (CR-3 보안 게이트) — PENDING 연락처를 고객사에 매핑 후 승인/거절
import { useState } from 'react'
import { UserCirclePlus } from '@phosphor-icons/react'
import { useAuth } from '../../app/AuthProvider'
import { useToast } from '../../components/Toast'
import { EmptyState } from '../../components/EmptyState'
import { SkeletonTableRows } from '../../components/Skeleton'
import { useClientOptions } from '../../lib/api/queries'
import { fmtDateTime } from '../../lib/format'
import type { KakaoContact } from '../../types'
import { useUpdateKakaoContact } from './api'

interface PendingContactsProps {
  contacts: KakaoContact[]
  isLoading: boolean
}

export function PendingContacts({ contacts, isLoading }: PendingContactsProps) {
  const { user } = useAuth()
  const { showToast } = useToast()
  const { data: clients = [] } = useClientOptions()
  const update = useUpdateKakaoContact()

  // MANAGER 미만은 승인/거절 버튼 숨김 (조회만)
  const canApprove = user?.role === 'ADMIN' || user?.role === 'MANAGER'

  /** contact_id → 매핑할 client_id 선택 상태 */
  const [mapping, setMapping] = useState<Record<string, string>>({})
  /** 처리 중인 contact_id (버튼별 로딩 표시) */
  const [pendingId, setPendingId] = useState<string | null>(null)

  const handle = (contact: KakaoContact, status: 'APPROVED' | 'REJECTED') => {
    const clientId = mapping[contact.contact_id]
    if (status === 'APPROVED' && !clientId) {
      showToast('먼저 매핑할 고객사를 선택해 주세요.', 'info')
      return
    }
    setPendingId(contact.contact_id)
    update.mutate(
      {
        contactId: contact.contact_id,
        status,
        client_id: status === 'APPROVED' ? clientId : undefined,
      },
      {
        onSuccess: () => {
          showToast(
            status === 'APPROVED'
              ? `${contact.name ?? '연락처'} 님을 승인했습니다. 이후 대화가 해당 고객사 스레드에 기록됩니다.`
              : `${contact.name ?? '연락처'} 님의 요청을 거절했습니다.`,
            status === 'APPROVED' ? 'success' : 'info',
          )
        },
        onError: () => showToast('처리에 실패했습니다. 잠시 후 다시 시도해 주세요.', 'danger'),
        onSettled: () => setPendingId(null),
      },
    )
  }

  if (isLoading) {
    return (
      <div className="p-4">
        <SkeletonTableRows rows={3} />
      </div>
    )
  }

  if (contacts.length === 0) {
    return (
      <EmptyState
        icon={<UserCirclePlus size={32} />}
        title="승인 대기 요청이 없습니다"
        description="카카오 채널에서 신규 고객이 문의하면 신원 확인 후 이곳에서 승인할 수 있습니다."
        className="m-4 py-10"
      />
    )
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <p className="border-b border-slate-100 bg-amber-50/60 px-4 py-2.5 text-[11px] leading-relaxed text-amber-800">
        승인 전 고객에게는 AI가 일반 안내만 제공합니다. 신원 확인 후 고객사를 매핑해 승인해
        주세요.
        {!canApprove && ' (승인·거절은 MANAGER 이상 권한이 필요합니다)'}
      </p>
      {contacts.map((contact) => {
        const busy = pendingId === contact.contact_id && update.isPending
        return (
          <div key={contact.contact_id} className="border-b border-slate-100 p-4">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="text-sm font-bold text-slate-900">{contact.name ?? '이름 미상'}</span>
              <span className="text-[11px] text-slate-400">
                요청 {fmtDateTime(contact.requested_at ?? contact.created_at)}
              </span>
            </div>
            <p className="mb-2 text-xs text-slate-500">
              {contact.phone ?? '연락처 미확인'}
              {contact.memo ? ` · ${contact.memo}` : ''}
            </p>
            {canApprove && (
              <div className="flex items-center gap-2">
                <select
                  value={mapping[contact.contact_id] ?? ''}
                  onChange={(e) =>
                    setMapping((prev) => ({ ...prev, [contact.contact_id]: e.target.value }))
                  }
                  disabled={busy}
                  className="h-8 min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700 focus:border-slate-400 focus:outline-none"
                  aria-label="매핑할 고객사 선택"
                >
                  <option value="">고객사 선택…</option>
                  {clients.map((c) => (
                    <option key={c.client_id} value={c.client_id}>
                      {c.company_name}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => handle(contact, 'APPROVED')}
                  disabled={busy || !mapping[contact.contact_id]}
                  className="shrink-0 rounded-md bg-slate-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
                >
                  승인
                </button>
                <button
                  type="button"
                  onClick={() => handle(contact, 'REJECTED')}
                  disabled={busy}
                  className="shrink-0 rounded-md border border-rose-200 px-3 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 disabled:opacity-50"
                >
                  거절
                </button>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
