// SCR-04 보안 reveal 흐름 — POST /assets/{id}/reveal-auth → 평문 일시 표시 → 자동 숨김
// 평문은 컴포넌트 state에만 보관(전역 상태·스토리지 금지), 타이머 만료 시 즉시 제거.
import { useCallback, useEffect, useRef, useState } from 'react'
import { isAxiosError } from 'axios'
import { api } from '../../lib/api/client'
import { usePrivacy } from '../../app/PrivacyProvider'
import { useToast } from '../../components/Toast'
import type { RevealAuthResponse } from '../../types'

interface RevealedState {
  assetId: string
  value: string
}

export function useRevealAuth() {
  // reveal 유지 시간: PC 5초 / 모바일·태블릿 3초 (§7)
  const { revealDurationMs, maskEpoch } = usePrivacy()
  const { showToast } = useToast()
  const [revealed, setRevealed] = useState<RevealedState | null>(null)
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  /** 평문 즉시 제거 (마스킹 복귀) */
  const hide = useCallback(() => {
    clearTimer()
    setRevealed(null)
  }, [])

  // 보안 토글 재활성화 시 전체 초기화 + 언마운트 시 평문 제거
  useEffect(() => hide(), [maskEpoch, hide])
  useEffect(() => {
    return () => {
      clearTimer()
    }
  }, [])

  const reveal = useCallback(
    async (assetId: string) => {
      setLoadingId(assetId)
      try {
        const { data } = await api.post<RevealAuthResponse>(`/assets/${assetId}/reveal-auth`)
        clearTimer()
        setRevealed({ assetId, value: data.auth_value })
        // 만료 시 state에서 평문 제거
        timerRef.current = setTimeout(() => setRevealed(null), revealDurationMs)
      } catch (error) {
        if (isAxiosError(error) && error.response?.status === 503) {
          showToast('암호화 키가 설정되지 않아 조회할 수 없습니다.', 'danger')
        } else {
          showToast('접속 정보를 불러오지 못했습니다.', 'danger')
        }
      } finally {
        setLoadingId(null)
      }
    },
    [revealDurationMs, showToast],
  )

  return {
    /** 현재 평문 표시 중인 자산 (한 번에 1건) */
    revealed,
    /** reveal 요청 진행 중인 자산 ID */
    loadingId,
    reveal,
    hide,
  }
}
