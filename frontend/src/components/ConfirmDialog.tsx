import type { ReactNode } from 'react'
import { CircleNotch } from '@phosphor-icons/react'
import { Modal } from './Modal'

interface ConfirmDialogProps {
  open: boolean
  title: string
  /** 본문 설명 */
  message?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** danger: 빨간 확인 버튼 (발송·비활성화 등 되돌리기 어려운 액션) */
  danger?: boolean
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = '확인',
  cancelLabel = '취소',
  danger = false,
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      size="sm"
      footer={
        <>
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-white/5 disabled:opacity-60"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className={`flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold disabled:opacity-60 ${
              danger
                ? 'bg-rose-500/90 text-white hover:bg-rose-500'
                : 'bg-snow text-graphite hover:bg-white/90'
            }`}
          >
            {loading && <CircleNotch size={14} className="animate-spin" />}
            {confirmLabel}
          </button>
        </>
      }
    >
      <div className="text-sm leading-relaxed text-ash">{message}</div>
    </Modal>
  )
}
