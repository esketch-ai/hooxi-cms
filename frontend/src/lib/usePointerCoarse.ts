// 터치 기기(pointer: coarse) 감지 훅 — 태블릿 현장 기능(카메라 촬영·서명) 노출 게이트
// PrivacyProvider의 matchMedia 패턴과 동일 (마운트 시 1회 판정, PC는 false)
import { useMemo } from 'react'

export function usePointerCoarse(): boolean {
  return useMemo(
    () =>
      typeof window !== 'undefined' &&
      window.matchMedia('(pointer: coarse)').matches,
    [],
  )
}
