import { useEffect, useRef, useState } from 'react'
import {
  Bell,
  List,
  MagnifyingGlass,
  ShieldCheck,
  ShieldSlash,
} from '@phosphor-icons/react'
import { usePrivacy } from '../../app/PrivacyProvider'
import { EmptyState } from '../../components/EmptyState'

interface HeaderProps {
  onOpenMobileMenu: () => void
}

export function Header({ onOpenMobileMenu }: HeaderProps) {
  const { privacyOn, togglePrivacy } = usePrivacy()
  const [notifOpen, setNotifOpen] = useState(false)
  const notifRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!notifOpen) return
    const onClick = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotifOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [notifOpen])

  return (
    <header className="sticky top-0 z-40 flex h-16 shrink-0 items-center gap-3 border-b border-hairline bg-graphite/80 px-4 backdrop-blur lg:px-6">
      {/* 햄버거 (모바일·태블릿) */}
      <button
        type="button"
        onClick={onOpenMobileMenu}
        className="rounded-md p-2 text-smoke hover:bg-white/5 hover:text-bone lg:hidden"
        aria-label="전체 메뉴 열기"
      >
        <List size={22} />
      </button>

      {/* 통합 검색 (동작은 P1 — placeholder만) */}
      <div className="relative max-w-md flex-1">
        <MagnifyingGlass
          size={16}
          className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-slatey"
        />
        <input
          type="search"
          placeholder="고객사명·연락처·이슈 통합 검색"
          className="h-9 w-full rounded-lg border border-hairline bg-white/5 pr-3 pl-9 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
          aria-label="통합 검색"
        />
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        {/* 보안 모드 토글 */}
        <button
          type="button"
          onClick={togglePrivacy}
          className="flex items-center gap-2 rounded-lg border border-hairline px-2.5 py-1.5 hover:bg-white/5"
          title={privacyOn ? '보안 모드 켜짐 — 민감 데이터 마스킹 중' : '보안 모드 꺼짐'}
          aria-pressed={privacyOn}
        >
          {privacyOn ? (
            <ShieldCheck size={18} weight="fill" className="text-bone" />
          ) : (
            <ShieldSlash size={18} className="text-slatey" />
          )}
          <span className="hidden text-xs font-medium text-ash sm:inline">
            보안 모드
          </span>
          {/* 스위치 */}
          <span
            className={`relative inline-flex h-4.5 w-8 items-center rounded-full transition-colors ${
              privacyOn ? 'bg-snow' : 'bg-white/20'
            }`}
            aria-hidden="true"
          >
            <span
              className={`inline-block h-3.5 w-3.5 rounded-full transition-transform ${
                privacyOn ? 'translate-x-4 bg-graphite' : 'translate-x-0.5 bg-bone'
              }`}
            />
          </span>
        </button>

        {/* 알림 벨 (빈 패널) */}
        <div className="relative" ref={notifRef}>
          <button
            type="button"
            onClick={() => setNotifOpen((v) => !v)}
            className="rounded-md p-2 text-smoke hover:bg-white/5 hover:text-bone"
            aria-label="알림"
          >
            <Bell size={20} />
          </button>
          {notifOpen && (
            <div className="animate-fade-in absolute right-0 mt-2 w-80 rounded-3xl border border-hairline bg-graphite p-2">
              <p className="px-3 py-2 text-sm font-semibold text-bone">알림</p>
              <EmptyState
                icon={<Bell size={28} />}
                title="새 알림이 없습니다"
                description="긴급 이슈·보고서 마감·카카오 이관 대기 알림이 여기에 표시됩니다."
                className="border-0 py-8"
              />
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
