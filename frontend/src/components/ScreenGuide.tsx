// 화면 관점 안내 배너 — 정산·재무 화면이 스스로 설명하도록(관점·목적·정합·관점전환).
// 배경: 같은 원천(전기버스 차량 → 감축량·예상지급액)을 다른 축(차량/사업/운수사/정산상태/전사)
// 으로 묶은 것이라 정합하지만, 화면이 그 사실을 말해주지 않으면 중복처럼 보인다.
// PageHeader 바로 아래에 은은하게(항상 노출, 작게) 배치한다.
import type { ReactNode } from 'react'
import { Info } from '@phosphor-icons/react'
import { Link } from 'react-router-dom'

interface ScreenGuideProps {
  /** 이 화면의 관점(집계 축) — 배지로 표기 (예: '차량 1대 단위') */
  perspective?: string
  /** 설명 문구(목적·정합 안내) */
  children: ReactNode
  /** 관점 전환 링크 — 같은 원천을 다른 축으로 보는 화면들 */
  links?: { label: string; to: string }[]
}

export function ScreenGuide({ perspective, children, links }: ScreenGuideProps) {
  return (
    <div className="flex gap-3 rounded-2xl border border-hairline bg-elevate px-4 py-3">
      <Info size={18} className="mt-0.5 shrink-0 text-slatey" />
      <div className="flex flex-1 flex-col gap-1.5">
        {perspective && (
          <span className="inline-flex w-fit items-center rounded-full border border-hairline bg-elevate-strong px-2 py-0.5 text-xs font-medium text-ash">
            관점 · {perspective}
          </span>
        )}
        <p className="text-sm leading-relaxed text-ash">{children}</p>
        {links && links.length > 0 && (
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slatey">
            <span>관점 전환</span>
            {links.map((l) => (
              <Link
                key={l.to}
                to={l.to}
                className="font-medium text-ash underline decoration-hairline underline-offset-2 hover:text-bone"
              >
                {l.label}
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
