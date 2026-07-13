// 공통 코드 색상 팔레트 — 상태 배지·지도 마커·칸반 도트의 단일 색상 소스.
// tb_code.color(시맨틱명)를 여기의 className/hex로 해석한다. 백엔드 PALETTE_COLORS와 일치.
// Tailwind 클래스는 이 파일에 리터럴로 존재해야 JIT가 포함한다.

export type PaletteColor =
  | 'emerald'
  | 'amber'
  | 'rose'
  | 'blue'
  | 'purple'
  | 'gray'
  | 'sky'
  | 'teal'
  | 'indigo'
  | 'yellow'

interface PaletteSpec {
  /** 배지용 Tailwind 클래스(연한 배경+테두리) */
  badge: string
  /** 칸반 도트·스와치용 진한 배경 */
  dot: string
  /** 지도 마커 등 인라인 스타일용 hex */
  hex: string
  /** 팔레트 선택 UI 표시명 */
  label: string
}

const GRAY_BADGE = 'bg-elevate-strong text-ash border-hairline'

export const CODE_PALETTE: Record<PaletteColor, PaletteSpec> = {
  emerald: { badge: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-400/25', dot: 'bg-emerald-500', hex: '#10b981', label: '초록' },
  amber: { badge: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-400/25', dot: 'bg-amber-500', hex: '#f59e0b', label: '주황' },
  rose: { badge: 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-400/25', dot: 'bg-rose-500', hex: '#f43f5e', label: '빨강' },
  blue: { badge: 'bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-400/25', dot: 'bg-blue-500', hex: '#3b82f6', label: '파랑' },
  purple: { badge: 'bg-purple-500/15 text-purple-700 dark:text-purple-300 border-purple-400/25', dot: 'bg-purple-500', hex: '#a855f7', label: '보라' },
  gray: { badge: GRAY_BADGE, dot: 'bg-gray-400', hex: '#6b7280', label: '회색' },
  sky: { badge: 'bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-400/25', dot: 'bg-sky-500', hex: '#0ea5e9', label: '하늘' },
  teal: { badge: 'bg-teal-500/15 text-teal-700 dark:text-teal-300 border-teal-400/25', dot: 'bg-teal-500', hex: '#14b8a6', label: '청록' },
  indigo: { badge: 'bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 border-indigo-400/25', dot: 'bg-indigo-500', hex: '#6366f1', label: '남색' },
  yellow: { badge: 'bg-yellow-500/15 text-yellow-700 dark:text-yellow-300 border-yellow-400/25', dot: 'bg-yellow-500', hex: '#eab308', label: '노랑' },
}

export const PALETTE_ORDER: PaletteColor[] = [
  'emerald', 'blue', 'amber', 'rose', 'purple', 'teal', 'sky', 'indigo', 'yellow', 'gray',
]

function spec(color?: string | null): PaletteSpec | undefined {
  return color ? CODE_PALETTE[color as PaletteColor] : undefined
}

/** 배지 클래스 — 색상 미지정/미지원이면 회색 폴백 */
export function badgeClassOf(color?: string | null): string {
  return spec(color)?.badge ?? GRAY_BADGE
}

/** 칸반 도트 클래스 */
export function dotClassOf(color?: string | null): string {
  return spec(color)?.dot ?? CODE_PALETTE.gray.dot
}

/** 지도 마커 hex */
export function hexOf(color?: string | null): string {
  return spec(color)?.hex ?? CODE_PALETTE.gray.hex
}
