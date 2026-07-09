import { useEffect, useRef, useState } from 'react'
import { usePrivacy } from '../app/PrivacyProvider'

export type SensitiveType = 'money' | 'rate' | 'secret' | 'text'

interface SensitiveDataProps {
  type: SensitiveType
  value: string | number
  className?: string
}

// 표기 통일 (01_COMMON §3): 금액 ₩ ••••••• / 비율 ••• % / 시크릿 •••••••• / 텍스트 blur
const MASKS: Record<Exclude<SensitiveType, 'text'>, string> = {
  money: '₩ •••••••',
  rate: '••• %',
  secret: '••••••••',
}

export function SensitiveData({ type, value, className = '' }: SensitiveDataProps) {
  const { privacyOn, maskEpoch, revealDurationMs, isPointerFine } = usePrivacy()
  const [revealed, setRevealed] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  // 토글 재활성화(OFF→ON) 시 reveal 전체 초기화
  useEffect(() => {
    setRevealed(false)
    clearTimer()
  }, [maskEpoch])

  useEffect(() => clearTimer, [])

  if (!privacyOn) {
    return <span className={className}>{value}</span>
  }

  const reveal = () => {
    setRevealed(true)
    clearTimer()
    // PC 5초 / 모바일·태블릿 3초 후 자동 재마스킹
    timerRef.current = setTimeout(() => setRevealed(false), revealDurationMs)
  }

  const handleMouseLeave = () => {
    // PC: mouse-leave 시 즉시 재마스킹
    if (isPointerFine && revealed) {
      clearTimer()
      setRevealed(false)
    }
  }

  if (revealed) {
    return (
      <span
        className={`cursor-pointer rounded bg-amber-50 px-1 ${className}`}
        onMouseLeave={handleMouseLeave}
        title="잠시 후 자동으로 다시 가려집니다"
      >
        {value}
      </span>
    )
  }

  if (type === 'text') {
    return (
      <span
        role="button"
        tabIndex={0}
        onClick={reveal}
        onKeyDown={(e) => e.key === 'Enter' && reveal()}
        className={`cursor-pointer rounded bg-slate-100 px-1 blur-[5px] select-none ${className}`}
        title="클릭하여 일시 표시"
        aria-label="민감 정보 — 클릭하여 일시 표시"
      >
        {value}
      </span>
    )
  }

  return (
    <span
      role="button"
      tabIndex={0}
      onClick={reveal}
      onKeyDown={(e) => e.key === 'Enter' && reveal()}
      className={`cursor-pointer rounded bg-slate-100 px-1 font-mono tracking-tight text-slate-500 select-none ${className}`}
      title="클릭하여 일시 표시"
      aria-label="민감 정보 — 클릭하여 일시 표시"
    >
      {MASKS[type]}
    </span>
  )
}
