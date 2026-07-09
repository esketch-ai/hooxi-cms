// 상태 배지 사전 (SCREEN_DESIGN_PLAN §3.3) — 도메인별 매핑 상수, 색+텍스트 병기(GAN D10)

export type BadgeDomain =
  | 'contract' // 계약 상태
  | 'assetStatus' // 자산 운영
  | 'assetType' // 자산 소분류
  | 'activity' // 활동 유형
  | 'issue' // 이슈 상태
  | 'project' // 사업 진행
  | 'settlement' // 정산 상태
  | 'report' // 보고서 상태
  | 'retention' // 리텐션 8단계

interface BadgeSpec {
  label: string
  className: string
}

const green = 'bg-emerald-50 text-emerald-700 border-emerald-200'
const yellow = 'bg-amber-50 text-amber-700 border-amber-200'
const red = 'bg-rose-50 text-rose-700 border-rose-200'
const blue = 'bg-blue-50 text-blue-700 border-blue-200'
const purple = 'bg-purple-50 text-purple-700 border-purple-200'
const gray = 'bg-slate-100 text-slate-600 border-slate-200'
const grayStrike = `${gray} line-through`

export const BADGE_DICTIONARY: Record<BadgeDomain, Record<string, BadgeSpec>> = {
  contract: {
    ACTIVE: { label: '계약중', className: green },
    HOLD: { label: '보류', className: yellow },
    END: { label: '종료', className: gray },
  },
  assetStatus: {
    ACTIVE: { label: '운영중', className: green },
    INACTIVE: { label: '비활성', className: gray },
    ERROR: { label: '오류', className: red },
  },
  assetType: {
    ICE: { label: '내연기관', className: blue },
    EV: { label: '전기차', className: gray },
    SOLAR: { label: '태양광', className: yellow },
    HEATPUMP: { label: '히트펌프', className: 'bg-amber-50 text-amber-800 border-amber-300' },
  },
  activity: {
    CALL: { label: '전화', className: green },
    MEETING: { label: '미팅', className: blue },
    SITE_VISIT: { label: '현장방문', className: purple },
    EMAIL: { label: '이메일', className: gray },
    ISSUE: { label: '이슈', className: red },
    KAKAO: { label: '카카오', className: yellow },
  },
  issue: {
    OPEN: { label: '접수', className: red },
    IN_PROGRESS: { label: '처리중', className: yellow },
    HOLD: { label: '보류', className: gray },
    CLOSED: { label: '완료', className: green },
  },
  project: {
    // 백엔드 저장 값(한국어 — schemas._PROJECT_STATUS_PATTERN)
    기획: { label: '기획', className: gray },
    등록완료: { label: '등록완료', className: blue },
    모니터링: { label: '모니터링', className: blue },
    검증: { label: '검증', className: purple },
    발급완료: { label: '발급완료', className: green },
    // 영문 코드 호환
    PLANNING: { label: '기획', className: gray },
    REGISTERED: { label: '등록', className: blue },
    MONITORING: { label: '모니터링', className: blue },
    VERIFICATION: { label: '검증', className: purple },
    ISSUED: { label: '발급완료', className: green },
  },
  settlement: {
    STANDBY: { label: '대기', className: gray },
    BILLED: { label: '청구', className: yellow },
    COMPLETED: { label: '입금완료', className: green },
  },
  report: {
    STANDBY: { label: '미착수', className: gray },
    WRITING: { label: '작성중', className: blue },
    REVIEW: { label: '내부검토', className: purple },
    SENT: { label: '발송완료', className: green },
    CONFIRMED: { label: '고객확인 ✓', className: green },
    CANCELED: { label: '취소', className: grayStrike },
    MERGED: { label: '병합 이관', className: grayStrike },
  },
  retention: {
    AWARENESS: { label: '인지', className: gray },
    INTEREST: { label: '관심', className: 'bg-slate-100 text-slate-700 border-slate-300' },
    REVIEW: { label: '검토', className: blue },
    DECISION: { label: '구매결정', className: 'bg-blue-100 text-blue-800 border-blue-300' },
    ONBOARDING: { label: '온보딩', className: 'bg-emerald-50 text-emerald-600 border-emerald-200' },
    UTILIZATION: { label: '활용', className: green },
    RENEWAL: { label: '재계약', className: 'bg-emerald-100 text-emerald-700 border-emerald-300' },
    EXPANSION: { label: '확장', className: 'bg-emerald-100 text-emerald-800 border-emerald-300' },
  },
}

interface StatusBadgeProps {
  domain: BadgeDomain
  value: string
  className?: string
}

export function StatusBadge({ domain, value, className = '' }: StatusBadgeProps) {
  const spec = BADGE_DICTIONARY[domain]?.[value] ?? {
    label: value,
    className: gray,
  }
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${spec.className} ${className}`}
    >
      {spec.label}
    </span>
  )
}
