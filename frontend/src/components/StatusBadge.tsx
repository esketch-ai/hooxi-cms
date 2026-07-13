// 상태 배지 사전 (SCREEN_DESIGN_PLAN §3.3) — 도메인별 매핑 상수, 색+텍스트 병기(GAN D10)
// 관리 도메인은 공통 코드 마스터(tb_code)에서 라벨·색상을 우선 조회하고, 미로딩·미관리
// 도메인은 아래 정적 사전으로 폴백한다.
import { useCodeLookup } from '../app/CodeProvider'
import { badgeClassOf } from '../lib/codePalette'

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

const green = 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-400/25'
const yellow = 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-400/25'
const red = 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-400/25'
const blue = 'bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-400/25'
const purple = 'bg-purple-500/15 text-purple-700 dark:text-purple-300 border-purple-400/25'
const gray = 'bg-elevate-strong text-ash border-hairline'
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
    HEATPUMP: { label: '히트펌프', className: 'bg-amber-500/20 text-amber-800 dark:text-amber-200 border-amber-400/30' },
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
    INTEREST: { label: '관심', className: 'bg-elevate-strong text-bone border-hairline-strong' },
    REVIEW: { label: '검토', className: blue },
    DECISION: { label: '구매결정', className: 'bg-blue-500/20 text-blue-800 dark:text-blue-200 border-blue-400/30' },
    ONBOARDING: { label: '온보딩', className: green },
    UTILIZATION: { label: '활용', className: green },
    RENEWAL: { label: '재계약', className: 'bg-emerald-500/20 text-emerald-800 dark:text-emerald-200 border-emerald-400/30' },
    EXPANSION: { label: '확장', className: 'bg-emerald-500/25 text-emerald-800 dark:text-emerald-200 border-emerald-400/35' },
  },
}

// 공통 코드 마스터로 관리되는 도메인 → tb_code 카테고리 매핑.
// 여기 있으면 마스터(라벨·색상) 우선, 없으면 아래 정적 사전으로 폴백.
const DOMAIN_TO_CATEGORY: Partial<Record<BadgeDomain, string>> = {
  contract: 'CONTRACT_STATUS',
  activity: 'ACTIVITY_TYPE',
  assetStatus: 'ASSET_STATUS',
  assetType: 'ASSET_TYPE',
  project: 'PROJECT_STATUS',
  settlement: 'SETTLEMENT_STATUS',
  issue: 'ISSUE_STATUS',
}

interface StatusBadgeProps {
  domain: BadgeDomain
  value: string
  className?: string
}

export function StatusBadge({ domain, value, className = '' }: StatusBadgeProps) {
  const lookup = useCodeLookup()
  const category = DOMAIN_TO_CATEGORY[domain]
  const master = category ? lookup(category, value) : undefined

  const spec: BadgeSpec = master
    ? { label: master.label, className: badgeClassOf(master.color) }
    : BADGE_DICTIONARY[domain]?.[value] ?? { label: value, className: gray }

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${spec.className} ${className}`}
    >
      {spec.label}
    </span>
  )
}
