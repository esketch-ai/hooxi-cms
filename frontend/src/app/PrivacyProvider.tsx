import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

const STORAGE_KEY = 'hooxi_privacy_mode'

interface PrivacyContextValue {
  /** 보안 모드 ON = 민감 데이터 마스킹 (기본 ON) */
  privacyOn: boolean
  togglePrivacy: () => void
  /**
   * OFF→ON 전환 시 증가 — 개별 reveal 상태 전체 초기화 신호
   * (01_COMMON §3: 토글 재활성화 시 reveal 전체 초기화)
   */
  maskEpoch: number
  /** reveal 유지 시간(ms): PC 5초 / 모바일·태블릿 3초 */
  revealDurationMs: number
  /** PC(pointer:fine) 여부 — mouse-leave 재마스킹 적용 대상 */
  isPointerFine: boolean
}

const PrivacyContext = createContext<PrivacyContextValue | null>(null)

function readInitial(): boolean {
  const saved = sessionStorage.getItem(STORAGE_KEY)
  return saved === null ? true : saved === 'on'
}

export function PrivacyProvider({ children }: { children: ReactNode }) {
  const [privacyOn, setPrivacyOn] = useState<boolean>(readInitial)
  const [maskEpoch, setMaskEpoch] = useState(0)

  const isPointerFine = useMemo(
    () =>
      typeof window !== 'undefined' &&
      window.matchMedia('(pointer: fine)').matches,
    [],
  )

  const togglePrivacy = useCallback(() => {
    setPrivacyOn((prev) => {
      const next = !prev
      sessionStorage.setItem(STORAGE_KEY, next ? 'on' : 'off')
      if (next) setMaskEpoch((e) => e + 1) // reveal 전체 초기화
      return next
    })
  }, [])

  const value = useMemo<PrivacyContextValue>(
    () => ({
      privacyOn,
      togglePrivacy,
      maskEpoch,
      revealDurationMs: isPointerFine ? 5000 : 3000,
      isPointerFine,
    }),
    [privacyOn, togglePrivacy, maskEpoch, isPointerFine],
  )

  return (
    <PrivacyContext.Provider value={value}>{children}</PrivacyContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function usePrivacy(): PrivacyContextValue {
  const ctx = useContext(PrivacyContext)
  if (!ctx) throw new Error('usePrivacy must be used within PrivacyProvider')
  return ctx
}
