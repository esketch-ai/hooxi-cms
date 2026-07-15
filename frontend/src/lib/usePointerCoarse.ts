// 터치 입력 기기 감지 훅 — 태블릿 현장 기능(카메라 촬영·서명) 노출 게이트
// (pointer: coarse) 단독으로는 부족: iPadOS는 데스크톱 클래스 브라우징·트랙패드
// 연결 시 주 포인터를 fine으로 보고할 수 있다. any-pointer와 maxTouchPoints
// (iPadOS는 데스크톱 위장 중에도 5를 보고)를 함께 본다. 터치 없는 PC는 false.
import { useMemo } from 'react'

export function usePointerCoarse(): boolean {
  return useMemo(() => {
    if (typeof window === 'undefined') return false
    return (
      window.matchMedia('(any-pointer: coarse)').matches ||
      (typeof navigator !== 'undefined' && navigator.maxTouchPoints > 0)
    )
  }, [])
}
