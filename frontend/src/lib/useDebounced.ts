// 디바운스 값 훅 — 검색 입력 등 연타 시 서버 요청 절제 (기본 300ms)
import { useEffect, useState } from 'react'

export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}
