// 데이터 업로드 센터(개편 P2) — 흩어진 13개 업로드 진입점을 한 화면에서 안내·진입.
// 각 업로드는 기존 화면/엔드포인트를 재사용(딥링크). "무엇을 어디서 올리는지"의 단일 지도.
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Buildings,
  Bus,
  ChartLineUp,
  Lightning,
  Receipt,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { useAuth } from '../../app/AuthProvider'

interface UploadEntry {
  name: string
  desc: string
  format: string
  to: string
  where: string
  roles?: string[]
}
interface UploadCategory {
  label: string
  icon: typeof Buildings
  entries: UploadEntry[]
}

const CATEGORIES: UploadCategory[] = [
  {
    label: '고객사 · 차량 기초',
    icon: Buildings,
    entries: [
      { name: '고객사 마스터', desc: '운수사·건물 고객사 일괄 등록', format: '.xlsx 표준 양식(양식 다운로드 제공)', to: '/clients', where: '고객사 마스터 › 일괄 등록' },
      { name: '보유 차량 명부', desc: '운수사 보유 버스 원장(전국 단위)', format: '.xlsx 차량번호·차대·차명·연식·연료', to: '/clients', where: '고객사 상세 › 보유 차량' },
      { name: '계약대수 현황', desc: '월별 계약대수 원본 엑셀', format: '.xlsx (고객사×월) 대수', to: '/clients', where: '고객사 상세 › 계약대수 현황' },
      { name: '자산 · 연동', desc: '관제 연동 자산·설비', format: '.xlsx 표준 양식', to: '/assets', where: '자산·연동 마스터' },
    ],
  },
  {
    label: '감축 산정',
    icon: ChartLineUp,
    entries: [
      { name: '감축 레지스트리(KISA)', desc: '프로그램 참여 차량 원장', format: '.xlsx 베이스라인/전기/후보', to: '/registry', where: '감축 산정 워크벤치 › 차량 현황', roles: ['ADMIN', 'MANAGER', 'STAFF'] },
      { name: '산정 입력', desc: '연평균 주행·연료·충전 산정 입력', format: '.xlsx 차량번호·도입구분·차대번호', to: '/registry', where: '감축 산정 워크벤치 › 감축량 산정', roles: ['ADMIN', 'MANAGER', 'STAFF'] },
      { name: '민간투자비율', desc: '차량별 재무·자부담(민간비율 근거)', format: '.xlsx 출고가·자부담금·차량가액', to: '/registry', where: '감축 산정 워크벤치 › 민간투자비율', roles: ['ADMIN', 'MANAGER', 'STAFF'] },
      { name: '충전인프라', desc: '차고지·충전기·AC전력량계', format: '.xlsx 충전 인프라 대장', to: '/registry', where: '감축 산정 워크벤치 › 충전인프라', roles: ['ADMIN', 'MANAGER', 'STAFF'] },
    ],
  },
  {
    label: '운행 · 충전 로그',
    icon: Bus,
    entries: [
      { name: '취합본(WIDE)', desc: '담당자 정본 취합 엑셀', format: 'YYYY년MM월_운행일수/운행거리/충전량', to: '/registry', where: '감축 산정 워크벤치 › 운행·충전 로그', roles: ['ADMIN', 'MANAGER', 'STAFF'] },
      { name: '운수사 원본(다건)', desc: 'eTAS .xls · BMS취합 .xlsx 직접', format: '구조 자동판별(월=파일명)', to: '/registry', where: '감축 산정 워크벤치 › 운행·충전 로그', roles: ['ADMIN', 'MANAGER', 'STAFF'] },
      { name: 'Dropbox 자동 수집', desc: '지정 폴더 저장 → 자동 스캔·적재', format: '폴더 하위 .xls/.xlsx 재귀', to: '/registry', where: '감축 산정 워크벤치 › 운행·충전 로그', roles: ['ADMIN', 'MANAGER', 'STAFF'] },
    ],
  },
  {
    label: '충전량 수집 · 재무',
    icon: Lightning,
    entries: [
      { name: '충전 관제 계정', desc: '벤더 포털 계정 목록(비밀번호 암호화)', format: '.xlsx 구분·회사명·시스템·주소·아이디·비번', to: '/accounts', where: '계정 점검 › 충전계정 일괄등록', roles: ['ADMIN', 'MANAGER'] },
      { name: '세금계산서', desc: '국세청 HTML 자동반영/스캔', format: '.html 보안메일 · Dropbox 스캔', to: '/tax-invoices', where: '세금계산서 원장', roles: ['ADMIN', 'MANAGER', 'STAFF'] },
    ],
  },
]

export function DataImportCenterPage() {
  const { user } = useAuth()
  const role = user?.role
  const allowed = (roles?: string[]) => !roles || (role != null && roles.includes(role))

  return (
    <div className="space-y-5">
      <PageHeader
        title="데이터 업로드 센터"
        subtitle="차량·감축·운행·충전·재무 데이터를 올리는 모든 진입점을 한곳에서 — 각 항목은 담당 화면으로 이동합니다."
      />
      <div className="flex items-start gap-2.5 rounded-2xl border border-hairline bg-graphite px-4 py-3">
        <Receipt size={18} className="mt-0.5 shrink-0 text-slatey" />
        <p className="text-sm leading-relaxed text-ash">
          업로드는 각 도메인 화면에서 실행됩니다. 이 화면은 <span className="font-semibold text-bone">무엇을 어디서 올리는지</span> 안내하는 지도입니다.
          같은 데이터를 여러 번 올려도 안전하도록 대부분 <span className="font-semibold text-bone">중복 키 기준 갱신(upsert)</span>으로 처리됩니다.
        </p>
      </div>

      <div className="space-y-6">
        {CATEGORIES.map((cat) => {
          const entries = cat.entries.filter((e) => allowed(e.roles))
          if (entries.length === 0) return null
          const Icon = cat.icon
          return (
            <section key={cat.label}>
              <h2 className="mb-2.5 flex items-center gap-2 text-sm font-semibold text-bone">
                <Icon size={17} className="text-slatey" weight="bold" />
                {cat.label}
              </h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {entries.map((e) => (
                  <Link
                    key={e.name}
                    to={e.to}
                    className="group flex flex-col rounded-2xl border border-hairline bg-graphite p-4 transition-colors hover:border-hairline-strong hover:bg-elevate"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="text-sm font-semibold text-bone">{e.name}</h3>
                      <ArrowRight size={15} className="mt-0.5 shrink-0 text-slatey transition-transform group-hover:translate-x-0.5" />
                    </div>
                    <p className="mt-1 text-xs text-ash">{e.desc}</p>
                    <p className="mt-2 rounded-lg bg-elevate px-2 py-1 font-mono text-[10.5px] leading-snug text-slatey">{e.format}</p>
                    <p className="mt-2 text-[11px] text-slatey">위치: <span className="text-ash">{e.where}</span></p>
                  </Link>
                ))}
              </div>
            </section>
          )
        })}
      </div>
    </div>
  )
}
