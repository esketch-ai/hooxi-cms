// 권한 표현 게이트 — 인가 판정은 호출부(allow)가 담당하고, 여기선 표현만 통일한다.
// mode='hide'  : 액션 버튼용. 불허 시 인접 사유 텍스트 1줄(또는 null).
// mode='notice': 탭/영역용. 불허 시 PermissionNotice 전면 안내.
// (disable 모드는 PV-B 설정탭에서 필요 시 확장)
import type { ReactNode } from 'react'
import { PermissionNotice } from './PermissionNotice'

interface RoleGateProps {
  /** 허용 여부(호출부의 인가 판정 결과) */
  allow: boolean
  /** 불허 사유 — hide 모드에서 인접 텍스트로 노출 */
  reason?: string
  /** notice 모드의 안내 대상 기능명 */
  feature?: string
  mode?: 'hide' | 'notice'
  children: ReactNode
}

export function RoleGate({ allow, reason, feature, mode = 'hide', children }: RoleGateProps) {
  if (allow) return <>{children}</>

  if (mode === 'notice') {
    return <PermissionNotice feature={feature ?? '이 기능'} />
  }

  // hide 모드: 네이티브 title은 disabled 요소에서 안 뜨므로 사유는 인접 텍스트로.
  if (reason) return <span className="text-xs text-slatey">{reason}</span>
  return null
}
