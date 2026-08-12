// 사용자 가이드 — 콘텐츠 빌딩 블록 (허브+서브페이지 구조에서 공용 재사용)
// 기존 GuidePage.tsx의 블록을 마크업/클래스 그대로 추출한 것.
import type { ReactNode } from 'react'

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <span className="inline-block rounded-md border border-hairline bg-elevate-strong px-1.5 py-px text-xs font-semibold text-bone whitespace-nowrap">
      {children}
    </span>
  )
}

export function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-block rounded-full border border-hairline bg-elevate px-2.5 py-px text-xs font-medium text-bone whitespace-nowrap">
      {children}
    </span>
  )
}

export function Note({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="my-3 rounded-r-xl border-l-2 border-rose-500/70 bg-rose-500/5 px-4 py-2.5 text-sm text-ash">
      {title && <b className="text-bone">{title}: </b>}
      {children}
    </div>
  )
}

export function Flow({ children }: { children: ReactNode }) {
  return (
    <div className="my-3 rounded-xl border border-hairline bg-graphite px-5 py-4">
      <ol className="list-decimal space-y-1.5 pl-4 text-sm text-ash marker:text-slatey">
        {children}
      </ol>
    </div>
  )
}

export function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="my-3 overflow-x-auto rounded-xl border border-hairline">
      <table className="w-full min-w-[480px] text-sm">
        <thead>
          <tr className="border-b border-hairline bg-elevate">
            {head.map((h) => (
              <th key={h} className="px-3.5 py-2 text-left text-xs font-semibold text-slatey">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((cells, i) => (
            <tr key={i} className="border-b border-hairline align-top last:border-b-0">
              {cells.map((c, j) => (
                <td key={j} className="px-3.5 py-2 text-ash">
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Faq({ q, children }: { q: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="mb-1 text-sm font-semibold text-bone">{q}</h3>
      <p className="text-sm text-ash">{children}</p>
    </div>
  )
}
