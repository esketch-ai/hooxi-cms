import { useEffect, type ReactNode } from 'react'
import { X } from '@phosphor-icons/react'

interface DrawerProps {
  open: boolean
  onClose: () => void
  title?: ReactNode
  children: ReactNode
  footer?: ReactNode
  /** md=448 / lg=576 */
  size?: 'md' | 'lg'
}

const sizes = { md: 'max-w-md', lg: 'max-w-xl' }

/** 우측 슬라이드 패널 — 이슈 상세·보고서 행 상세 등 (플랜 §4.2) */
export function Drawer({ open, onClose, title, children, footer, size = 'md' }: DrawerProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true">
      <div
        className="absolute inset-0 bg-black/70"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={`absolute inset-y-0 right-0 flex w-full ${sizes[size]} animate-slide-in flex-col border-l border-hairline bg-graphite`}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-hairline px-5 py-4">
          <div className="min-w-0 flex-1 text-base font-semibold text-bone">{title}</div>
          <button
            type="button"
            onClick={onClose}
            className="ml-2 rounded-md p-1 text-smoke hover:bg-white/5 hover:text-bone"
            aria-label="닫기"
          >
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <div className="flex shrink-0 justify-end gap-2 border-t border-hairline px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}
