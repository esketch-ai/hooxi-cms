// 사용자 가이드 — 실무자 관점 업무 매뉴얼 (메뉴별 "언제 무엇을 누르는가")
// 정적 콘텐츠 화면. 기능 변경 시 이 문서와 Docs/USER_GUIDE.html을 함께 갱신한다.
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { PageHeader } from '../../components/PageHeader'

// ── 콘텐츠 빌딩 블록 ────────────────────────────────────────────────
function Kbd({ children }: { children: ReactNode }) {
  return (
    <span className="inline-block rounded-md border border-hairline bg-elevate-strong px-1.5 py-px text-xs font-semibold text-bone whitespace-nowrap">
      {children}
    </span>
  )
}

function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-block rounded-full border border-hairline bg-elevate px-2.5 py-px text-xs font-medium text-bone whitespace-nowrap">
      {children}
    </span>
  )
}

function Note({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="my-3 rounded-r-xl border-l-2 border-rose-500/70 bg-rose-500/5 px-4 py-2.5 text-sm text-ash">
      {title && <b className="text-bone">{title}: </b>}
      {children}
    </div>
  )
}

function Flow({ children }: { children: ReactNode }) {
  return (
    <div className="my-3 rounded-xl border border-hairline bg-graphite px-5 py-4">
      <ol className="list-decimal space-y-1.5 pl-4 text-sm text-ash marker:text-slatey">
        {children}
      </ol>
    </div>
  )
}

function Sec({
  id,
  eyebrow,
  title,
  children,
}: {
  id: string
  eyebrow: string
  title: string
  children: ReactNode
}) {
  return (
    <section id={`guide-${id}`} className="scroll-mt-4 border-b border-hairline pb-8 last:border-b-0">
      <p className="mb-0.5 text-[11px] font-bold tracking-widest text-red-600 uppercase dark:text-red-500">
        {eyebrow}
      </p>
      <h2 className="mb-3 text-lg font-semibold text-bone">{title}</h2>
      <div className="space-y-2 text-sm leading-relaxed text-ash [&_b]:text-bone [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5 [&_li]:marker:text-slatey">
        {children}
      </div>
    </section>
  )
}

function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
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

function Faq({ q, children }: { q: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="mb-1 text-sm font-semibold text-bone">{q}</h3>
      <p className="text-sm text-ash">{children}</p>
    </div>
  )
}

// ── 목차 정의 ───────────────────────────────────────────────────────
const TOC: { id: string; label: string }[] = [
  { id: 'start', label: '시작하기 · 권한' },
  { id: 'dashboard', label: '통합 현황판' },
  { id: 'clients', label: '고객사 관리' },
  { id: 'assets', label: '자산 · 수집 계정' },
  { id: 'histories', label: '활동 이력' },
  { id: 'issues', label: '이슈 보드' },
  { id: 'calendar', label: '일정 캘린더' },
  { id: 'reports', label: '월간 보고서 발송' },
  { id: 'segments', label: '세그먼트 발송' },
  { id: 'documents', label: '문서 아카이브' },
  { id: 'projects', label: '감축 사업 · 정산' },
  { id: 'chat', label: '카카오 상담' },
  { id: 'map', label: '관제 지도' },
  { id: 'settings', label: '환경 설정' },
  { id: 'faq', label: '자주 묻는 질문' },
]

export function GuidePage() {
  const [active, setActive] = useState('start')
  const contentRef = useRef<HTMLDivElement>(null)

  // 스크롤 위치 기반 현재 섹션 하이라이트
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (visible[0]) setActive(visible[0].target.id.replace('guide-', ''))
      },
      { rootMargin: '0px 0px -70% 0px' },
    )
    contentRef.current
      ?.querySelectorAll('section[id^="guide-"]')
      .forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [])

  const jump = (id: string) => {
    document.getElementById(`guide-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="사용자 가이드"
        subtitle="메뉴별 업무 흐름 — 언제, 무엇을 누르는가"
      />

      <div className="flex gap-8">
        {/* 목차 (데스크톱) */}
        <nav className="sticky top-4 hidden w-48 shrink-0 self-start lg:block" aria-label="가이드 목차">
          <p className="mb-2 px-2 text-xs font-semibold tracking-wider text-slatey uppercase">
            목차
          </p>
          <ul className="space-y-px border-l border-hairline">
            {TOC.map((t) => (
              <li key={t.id}>
                <button
                  type="button"
                  onClick={() => jump(t.id)}
                  className={`-ml-px block w-full border-l-2 px-3 py-1.5 text-left text-[13px] transition-colors ${
                    active === t.id
                      ? 'border-red-600 font-semibold text-bone dark:border-red-500'
                      : 'border-transparent text-slatey hover:text-ash'
                  }`}
                >
                  {t.label}
                </button>
              </li>
            ))}
          </ul>
        </nav>

        {/* 본문 */}
        <div ref={contentRef} className="min-w-0 max-w-3xl flex-1 space-y-8">
          <Sec id="start" eyebrow="Getting Started" title="시작하기 · 권한">
            <ul>
              <li>
                <b>로그인</b>: 회사 이메일(@hooxipartners.com)로 로그인합니다. 최초 로그인 시
                PIN(4~6자리)을 설정하고, 이후에는 이메일+PIN으로 접속합니다. 신규 가입은 관리자
                승인 후 활성화됩니다.
              </li>
              <li>
                <b>보안 모드</b>(상단 토글, 기본 ON): 금액·연락처·보수율이 화면에서 가려집니다.
                고객사 미팅 등 화면을 함께 볼 때 켠 상태로 쓰고, 가려진 값은 클릭하면 일시
                표시됩니다(표시 행위는 감사 기록됨).
              </li>
              <li>
                <b>테마</b>: 상단 달/해 아이콘으로 다크·라이트 전환.
              </li>
              <li>
                <b>태블릿</b>: 현장용 기능(카메라 촬영, 고객 확인 서명)은 터치 기기에서만 버튼이
                나타납니다. PC에는 의도적으로 없습니다.
              </li>
            </ul>
            <Table
              head={['역할', '할 수 있는 일']}
              rows={[
                [<Chip>실무 STAFF</Chip>, '고객사·자산·이력·보고서·발송 등 일상 업무 전부. 계정 정보 열람(감사 기록됨)'],
                [<Chip>팀장 MANAGER</Chip>, '+ 자산·사업 삭제, 정산 상태 변경, 사용자 목록'],
                [<Chip>관리자 ADMIN</Chip>, '+ 계정 승인·역할 변경, 공통 코드·시스템 설정·연동 관리, 백업·복구, 감사 로그'],
              ]}
            />
          </Sec>

          <Sec id="dashboard" eyebrow="SCR-01" title="통합 현황판 — 하루의 시작">
            <p>
              화면을 열면 <b>오늘의 액션</b>이 가장 위에 있습니다. 지연된 것 → 긴급 → 마감 임박 →
              오늘 일정 순서로 정렬되며, 항목을 누르면 해당 업무 화면으로 바로 이동합니다.
            </p>
            <ul>
              <li>
                <b>팀 전체 / 내 것</b> 토글로 범위를 전환합니다. 실무자는 "내 것"이 기본입니다.
              </li>
              <li>
                KPI 카드(관리 고객사·당월 보고서·긴급 이슈·계약 협의·예상 청구액)는{' '}
                <b>전부 클릭 가능</b> — 해당 관리 화면으로 이동합니다.
              </li>
              <li>
                "관리 고객사"는 <i>계약중</i> 고객사 수입니다. 이슈 보드의 "전체 고객사"(등록
                전체)와 기준이 다릅니다.
              </li>
            </ul>
          </Sec>

          <Sec id="clients" eyebrow="SCR-03" title="고객사 관리">
            <Flow>
              <li>
                <Kbd>신규 고객사 등록</Kbd> — 구분·회사명·사업자번호 입력.{' '}
                <b>같은 사업자번호는 등록이 차단</b>되고 기존 고객사명을 알려줍니다(하이픈 표기가
                달라도 잡아냅니다).
              </li>
              <li>
                주 담당자 이메일은 <b>보고서 발송의 기본 수신처</b>이므로 정확히 입력하세요.
              </li>
              <li>
                여러 곳을 한 번에 등록하려면 <Kbd>엑셀 일괄 등록</Kbd> — 아래 참조.
              </li>
            </Flow>
            <h3 className="pt-1 text-sm font-semibold text-bone">엑셀 일괄 등록</h3>
            <ul>
              <li>
                <Kbd>양식 다운로드</Kbd> — 한글 헤더(필수 항목 *)와 예시 행이 담긴 파일을 받습니다.
              </li>
              <li>
                구분·계약 상태 등은 화면에서 보는 <b>한글 그대로</b>("운수사") 적으면 됩니다. 담당
                PM은 이름으로. <b>예시 행은 지우지 않아도 자동 제외</b>됩니다.
              </li>
              <li>
                업로드하면 즉시 "총 N행 중 M건 등록 가능"과 행별 오류 사유가 표시됩니다.{' '}
                <b>오류 행은 건너뛰고 유효한 행만 등록</b>되므로, 실패분은 수정해서 다시 올리면
                됩니다.
              </li>
            </ul>
            <h3 className="pt-1 text-sm font-semibold text-bone">고객사 상세 (360°)</h3>
            <p>
              탭 6개로 그 고객의 모든 것을 봅니다: <b>개요</b>(기본 정보·계약·
              <i>보고서 수신자 관리</i>) · <b>활동 이력</b>(첨부·서명 표시) · <b>보고서·문서</b> ·{' '}
              <b>자산 및 연동</b> · <b>참여 사업·정산</b> · <b>상담</b>.
            </p>
            <Note title="수신자 관리">
              개요 탭에서 보고서 받는 사람(TO/CC)을 등록합니다. 수신자가 없으면 주 담당자 이메일로
              발송됩니다.
            </Note>
            <p>
              고객사는 삭제하지 않습니다 — 거래 종료 시 계약 상태를 <Chip>종료</Chip>로 바꾸면
              보고서 대상에서 자동 제외되고 기록은 보존됩니다.
            </p>
          </Sec>

          <Sec id="assets" eyebrow="SCR-04" title="자산 · 수집 계정">
            <ul>
              <li>
                <b>자산 등록</b>: 고객사별 차량·설비를 대분류/소분류/수량/제원으로 등록. 엑셀 일괄
                등록 지원(계정 비밀번호는 보안상 엑셀에 넣을 수 없음 — 등록 후 화면에서 개별 입력).
              </li>
              <li>
                <b>계정 정보</b>: 외부 기관 로그인 비밀번호·API 키는 암호화 저장되고 화면에는 절대
                평문으로 남지 않습니다. <Kbd>••••••••</Kbd>를 클릭하면 잠시 표시되고(감사 기록),
                자동으로 다시 가려집니다.
              </li>
              <li>
                <b>제원표 촬영</b>(태블릿): 현장에서 카메라 버튼으로 촬영하면 자동 압축되어 고객사
                문서함에 <code className="text-xs">제원표_자산명_날짜_시각</code>으로 적재됩니다.{' '}
                <Kbd>사진 보기</Kbd>는 PC에서도 가능합니다.
              </li>
              <li>
                <b>수집 계정 관리</b> 메뉴: 계정 보유 자산만 모아 봅니다. <b>매월 1일 자동 점검</b>
                이 사이트 접속 가능 여부를 확인해 이슈를 만들어 주며, <Kbd>지금 전체 점검</Kbd>으로
                즉시 실행할 수 있습니다.
              </li>
            </ul>
          </Sec>

          <Sec id="histories" eyebrow="SCR-05" title="활동 이력 — 모든 컨택의 기록">
            <p>
              전화·미팅·현장방문·이메일·카카오·이슈가 날짜별로 묶여 시간순으로 보입니다. 검색은
              고객사명·제목으로 전체 데이터에서 찾습니다.
            </p>
            <Flow>
              <li>
                <Kbd>이력 등록</Kbd> — 유형·고객사·제목·내용. 발신자를 모르는 인바운드 콜은 고객사
                없이 기록해 두고, 나중에 확인되면 행을 펼쳐 <Kbd>고객사 연결</Kbd>.
              </li>
              <li>
                현장 사진은 등록 폼에서 여러 장 첨부(태블릿은 촬영). <b>고객 확인 서명</b>은 행을
                펼쳐 서명 패드로 받습니다(태블릿).
              </li>
              <li>첨부·서명은 행을 펼치면 보이고, 제목을 누르면 다운로드 없이 바로 미리보기됩니다.</li>
            </Flow>
            <Note title="기록 불변 원칙">
              등록된 이력의 내용·일시는 수정·삭제할 수 없습니다(신뢰 보존). 예외는 두 가지뿐 —
              미지정 고객 연결, 이슈 담당자 인계. 둘 다 변경 흔적이 남습니다. 오기록은 새 이력으로
              바로잡아 주세요.
            </Note>
          </Sec>

          <Sec id="issues" eyebrow="SCR-02" title="이슈 보드 — 팀 공용 칸반">
            <ul>
              <li>
                카드를 끌어 <Chip>접수</Chip> → <Chip>처리중</Chip> → <Chip>보류</Chip> →{' '}
                <Chip>완료</Chip> 로 옮깁니다. 상태 변경은 코멘트에 자동 기록됩니다.
              </li>
              <li>
                카드를 누르면 상세 패널 — 고객사 바로가기, 담당자 전화 연결, 코멘트 스레드,{' '}
                <b>담당자 인계</b>(휴가·퇴사 시 셀렉트로 변경, 인계 코멘트 자동 기록).
              </li>
              <li>
                두 명이 같은 카드를 동시에 옮기면 한 명에게 "다른 사용자가 방금 변경했습니다 —
                새로고침" 안내가 뜹니다. 작업이 조용히 사라지지 않습니다.
              </li>
              <li>
                완료 칼럼은 최근 7일만 보여줍니다. 미처리 이슈는 아무리 오래돼도 사라지지 않으며,
                200건이 넘으면 경고 배지가 나타납니다.
              </li>
            </ul>
          </Sec>

          <Sec id="calendar" eyebrow="SCR-11" title="일정 캘린더">
            <ul>
              <li>
                일정 등록 시 고객사를 연결하면 완료 처리할 때 <b>활동 이력이 자동 생성</b>됩니다
                (내부 일정은 제외). 현장 주소를 입력하면 내비 연결의 원천이 됩니다.
              </li>
              <li>"매월 반복"을 체크하면 정기 일정으로 실체화됩니다.</li>
              <li>
                보고서 마감일 일정(<code className="text-xs">[자동] 보고서 마감</code>)은 발송
                대상이 생성될 때 자동으로 잡힙니다.
              </li>
            </ul>
          </Sec>

          <Sec id="reports" eyebrow="SCR-12" title="월간 보고서 발송 — 한 달 사이클">
            <Table
              head={['상태', '의미', '다음 행동']}
              rows={[
                [<Chip>미착수</Chip>, '이번 달 슬롯 생성됨', '보고서 파일 업로드'],
                [<Chip>작성중</Chip>, '파일 업로드됨(버전 자동 관리)', '검토 요청 또는 바로 승인'],
                [<Chip>내부검토</Chip>, '검토 중', '확인 후 발송 승인'],
                [<Chip>발송승인</Chip>, <b>월초 배치 자동 발송 대상</b>, '기다리거나 즉시 수동 발송'],
                [<Chip>발송완료</Chip>, '메일 발송됨(열람 추적 링크 포함)', '고객 확인 시 확인 처리'],
                [<Chip>고객확인</Chip>, '고객이 수신 확인', '완료 — 되돌릴 수 없음'],
                [<Chip>취소</Chip>, '이번 달 발송 안 함(사유 필수)', '필요 시 복원 → 처음부터 재진행'],
              ]}
            />
            <ul>
              <li>
                <b>대상 생성</b>: 구독 활성 + 수신 Y + 계약중 고객사의 이번 달 슬롯을 만듭니다.{' '}
                <b>매월 1일 배치가 자동 수행</b>하므로 평소엔 누를 일이 없고, 월 중 신규 고객을
                즉시 편입할 때만 사용합니다. 여러 번 눌러도 중복되지 않습니다.
              </li>
              <li>
                <b>버전과 고정본</b>: 재업로드하면 v1, v2… 로 쌓이고 발송은 최신본. 특정 버전을
                보내야 하면 상세에서 <Kbd>고정</Kbd> — 고정본이 우선 발송됩니다.
              </li>
              <li>
                <b>자동 발송</b>: 매월 1일 09:00 배치가 전월 <Chip>발송승인</Chip> 건을 일괄
                발송합니다. 승인 안 된 건은 건너뛰고, 실패 건은 승인 상태로 남아 다음 달
                재시도됩니다.
              </li>
              <li>
                <b>메일 문구</b>: 기본 템플릿은 환경 설정 &gt; 시스템 설정에서, 고객사별 커스텀은
                고객사 수정 폼에서. <code className="text-xs">{'{고객사명}'}</code>{' '}
                <code className="text-xs">{'{월}'}</code> 같은 변수가 자동 치환됩니다.
              </li>
              <li>발송 메일의 열람 링크를 고객이 열면 <Chip>고객확인</Chip> 후보로 기록됩니다.</li>
            </ul>
          </Sec>

          <Sec id="segments" eyebrow="Segment" title="세그먼트 발송 — 조건으로 묶어 일괄 발송">
            <p>
              월간 보고서와 달리 <b>대상 생성이 필요 없습니다</b>. 발송 순간의 조건 평가로 대상이
              정해지고, 전원에게 같은 공통 파일을 보냅니다. (예: "수도권 + 전기버스 사업 참여사
              전체에 사업 안내문 1부")
            </p>
            <Flow>
              <li>
                보고서 발송 관리 → <Kbd>세그먼트 발송</Kbd>
              </li>
              <li>
                왼쪽에서 조건 조합(지역·구분·계약·사업·자산·정산) — 오른쪽{' '}
                <b>"대상 N개사"가 실시간 갱신</b>됩니다. 수신자 없는 회사는 경고 배지, 계약 종료
                고객사는 상태 배지로 표시됩니다.
              </li>
              <li>
                문서함에서 파일 선택(복수 가능) → 제목·본문 확인 → <Kbd>발송</Kbd> → 확인
                다이얼로그(종료 고객사 포함 시 경고) → 고객사별 성공/실패가 이력으로 남습니다.
              </li>
              <li>
                자주 쓰는 조합은 <Kbd>현재 조합 저장</Kbd> — 칩 클릭 한 번으로 재사용. 저장된
                조합은 발송 시점에 다시 평가되므로 <b>신규 고객사도 자동 포함</b>됩니다.
              </li>
            </Flow>
          </Sec>

          <Sec id="documents" eyebrow="SCR-13" title="문서 아카이브">
            <ul>
              <li>
                모든 파일은 고객사별 폴더(계약서·보고서·현장사진·서명·양식·기타)로 자동 분류됩니다.
                폴더를 만들 일이 없습니다.
              </li>
              <li>
                <b>이미지·PDF는 제목 클릭으로 바로 미리보기</b> — 다운로드는 오른쪽 아이콘. 여러
                페이지 PDF는 미리보기에서 "새 탭에서 열기"가 편합니다.
              </li>
              <li>
                Dropbox 연동 후에는 회사 Dropbox에서도 같은 폴더 구조로 열람할 수 있습니다. 단 파일
                추가·이동은 반드시 CMS를 통해서 — Dropbox에 직접 넣은 파일은 CMS가 알지 못합니다.
              </li>
            </ul>
          </Sec>

          <Sec id="projects" eyebrow="SCR-06 · 07" title="감축 사업 · 정산">
            <Flow>
              <li>
                <b>사업 등록</b> → 참여 고객사 매핑(배분율 합계 100% 검증, 진행 바 표시) → 배출권
                단가 입력 → 예상 정산액은 서버가 자동 계산.
              </li>
              <li>
                <b>정산 흐름</b>: <Chip>대기</Chip> → <Kbd>청구서 발행</Kbd> → <Chip>청구</Chip> →{' '}
                <Kbd>입금 확인</Kbd> → <Chip>입금완료</Chip>. 역행은 불가합니다.
              </li>
              <li>단가 미입력이면 발행 버튼이 비활성 — 사업 상세에서 단가를 입력하면 활성화됩니다.</li>
            </Flow>
            <Note title="금액 동결">
              청구서를 발행한 순간 그 금액은 확정됩니다. 이후 단가를 바꿔도 청구·입금된 금액은
              변하지 않으며, 각 행의 <Kbd>이력</Kbd> 버튼에서 회차별 확정 금액을 언제든 확인할 수
              있습니다.
            </Note>
            <p>청구 이후에는 그 매핑의 배분율·보수율도 수정이 잠깁니다(정산 근거 보호).</p>
          </Sec>

          <Sec id="chat" eyebrow="SCR-08" title="카카오 상담 관제">
            <ul>
              <li>
                고객 카카오 문의가 스레드로 들어옵니다(5초 자동 갱신). AI 자동 응대 중인 건은{' '}
                <Kbd>직원 개입</Kbd>으로 넘겨받아 직접 답합니다.
              </li>
              <li>
                <b>승인 대기</b> 탭: 아직 고객사에 연결되지 않은 신규 연락처를 확인해 고객사와
                매칭합니다(고객사 주 담당자 연락처 기준 자동 후보 제시).
              </li>
              <li>상담 내용은 활동 이력에 연동되어 고객사 360°에서 함께 보입니다.</li>
            </ul>
          </Sec>

          <Sec id="map" eyebrow="SCR-09" title="관제 지도">
            <ul>
              <li>
                고객사를 계약 상태 색으로 전국 지도에 표시합니다. 필터(계약 상태·마지막 컨택 기준)와
                지역별 현황 제공.
              </li>
              <li>
                주소(지역)가 입력되지 않은 고객사는 지도에 표시되지 않습니다 — 화면 안내에 따라
                "지역 미지정"을 눌러 고객사 마스터에서 주소를 채우면 자동 표시됩니다.
              </li>
            </ul>
          </Sec>

          <Sec id="settings" eyebrow="SCR-14 · ADMIN" title="환경 설정 (관리자)">
            <ul>
              <li>
                <b>계정 관리</b>: 가입 승인, 역할 변경, 비활성화(즉시 접속 차단), PIN 초기화.
              </li>
              <li>
                <b>공통 코드 관리</b>: 구분·상태 등 분류값의 표시명·색상·순서를 관리합니다. 코드값은
                만든 후 바꿀 수 없고(데이터 보호), 표시명은 언제든 수정 가능 — 바꾸면 화면과 엑셀
                양식이 자동 추종합니다. 쓰지 않을 값은 삭제 대신 <b>비활성</b>으로.
              </li>
              <li>
                <b>시스템 설정</b>: 보고서 메일 기본 템플릿, 대시보드 퍼널 매핑, 점검 대상 기관 등.
              </li>
              <li>
                <b>연동 관리</b>: Gmail(발송)·Dropbox(파일)·SOLAPI(알림톡)·카카오 챗봇·네이버웍스
                자격증명 입력과 <Kbd>테스트</Kbd> 버튼. Dropbox는 OAuth 마법사가 안내합니다.{' '}
                <i>Gmail이 설정되지 않으면 모든 발송이 안전하게 차단됩니다.</i>
              </li>
              <li>
                <b>백업·복구</b>: 매일 자동 백업 + 수동 백업. 복구는 확인 문구 입력 필수.
              </li>
              <li>
                <b>감사 로그</b>: 누가 언제 무엇을 했는지 전 기록(계정 열람·발송·정산 변경·엑셀 등록
                등). 비밀값은 기록되지 않습니다.
              </li>
            </ul>
          </Sec>

          <Sec id="faq" eyebrow="FAQ" title="자주 묻는 질문">
            <div className="space-y-4">
              <Faq q='발송 버튼을 눌렀는데 "이메일 발송 기능이 아직 설정되지 않았습니다"라고 나와요'>
                Gmail 자격증명이 미설정 상태입니다. 관리자가 환경 설정 → 연동 관리에서 발신 계정을
                등록하면 즉시 발송됩니다. 그 전까지는 어떤 메일도 나가지 않으니 안심하세요.
              </Faq>
              <Faq q="두 명이 같은 걸 동시에 수정하면 어떻게 되나요?">
                먼저 저장한 사람이 반영되고, 나중 사람에게는 "다른 사용자가 방금 변경했습니다 —
                새로고침 후 다시 시도하세요"가 표시됩니다. 한쪽 작업이 조용히 사라지는 일은
                없습니다.
              </Faq>
              <Faq q="지도에 고객사가 안 보여요">
                주소(지역)가 비어 있으면 좌표를 잡을 수 없습니다. 고객사 마스터에서 주소를 입력하면
                자동 표시됩니다.
              </Faq>
              <Faq q="보고서를 잘못 승인했어요">
                발송 전이라면 상태를 내부검토/작성중으로 되돌리거나 취소(사유 입력)하면 됩니다.
                취소된 건은 배치가 발송하지 않습니다.
              </Faq>
              <Faq q="엑셀 업로드에서 일부만 등록됐어요">
                정상 동작입니다 — 오류 행만 건너뛰고 유효한 행은 등록됩니다. 결과 화면의 실패
                목록(행 번호·사유)을 보고 해당 행만 고쳐 다시 올리면 됩니다.
              </Faq>
              <Faq q="청구서 발행 후 단가가 바뀌면 금액은요?">
                청구된 금액은 동결됩니다. 정산 화면의 <Kbd>이력</Kbd>에서 청구 시점 금액을 언제든
                확인할 수 있고, 입금도 청구 금액 기준으로 기록됩니다.
              </Faq>
            </div>
            <p className="pt-4 text-xs text-slatey">
              기능이 바뀌면 이 가이드도 함께 갱신됩니다 · 문의: 시스템 관리자
            </p>
          </Sec>
        </div>
      </div>
    </div>
  )
}
