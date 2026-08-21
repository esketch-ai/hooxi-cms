// P2 자산관리 보고 — 운수사(고객사)별 정산 예정 요약. 부서 엑셀 보고의 시스템 대체.
// cf. FL-3 재무 원장은 '사업 grain', 여기는 '고객사 grain' — 참여사업·차량·예상지급액 집계(subtitle로 구분).
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Num } from '../../components/Num'
import {
  ChatCircleDots,
  CheckCircle,
  CircleNotch,
  Coins,
  DownloadSimple,
  EnvelopeSimple,
  TreeStructure,
  Truck,
  WarningCircle,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { ScreenGuide } from '../../components/ScreenGuide'
import { FilterBar, FilterSelect } from '../../components/FilterBar'
import { DataTable, type Column } from '../../components/DataTable'
import { KpiCard } from '../../components/KpiCard'
import { SensitiveData } from '../../components/SensitiveData'
import { EmptyState } from '../../components/EmptyState'
import { Modal } from '../../components/Modal'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { RoleGate } from '../../components/RoleGate'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import { useCodes, useClientOptions } from '../../lib/api/queries'
import { downloadExport } from '../../lib/export'
import { fmtMoney } from '../../lib/format'
import { useSettlementNoticePreview, useSettlementNoticeSend, useSettlementSummary } from './api'
import type {
  SettlementNoticeChannel,
  SettlementNoticePreviewItem,
  SettlementNoticeSendResult,
  SettlementNoticeType,
  SettlementSummaryFilters,
  SettlementSummaryRow,
} from './types'

/** 정수(참여수량·감축량 tCO₂ 등) 포맷 — nullable */
function fmtQty(value?: number | null, unit = ''): string {
  if (value === null || value === undefined) return '—'
  return `${Number(value).toLocaleString('ko-KR')}${unit}`
}

/** 금액 셀 — 값 있으면 SensitiveData(money), 없으면 '미정' 대시 */
function MoneyCell({ value }: { value: number | null }) {
  return value != null ? (
    <SensitiveData type="money" value={fmtMoney(value)} />
  ) : (
    <span className="text-smoke">미정</span>
  )
}

export function AssetReportPage() {
  const { user } = useAuth()
  const { showToast } = useToast()
  // OBSERVER(경영전략실)는 정책 A로 /clients가 백엔드 403 → 운수사 셀렉트 숨김 + 훅 미호출.
  const isObserver = user?.role === 'OBSERVER'
  const { data: clients = [] } = useClientOptions({ enabled: !isObserver })
  const { labelOf: clientTypeLabel, options: clientTypeOptions } = useCodes('CLIENT_TYPE')
  const { options: regionOptions } = useCodes('REGION')

  // 엑셀 내보내기 — 팀장 이상만(백엔드 require_role("MANAGER")과 정합). OBSERVER·STAFF엔 미노출.
  const isManagerUp = user?.role === 'ADMIN' || user?.role === 'MANAGER'
  const [exporting, setExporting] = useState(false)

  // 정산 통지(메일) — master.write(STAFF/MANAGER/ADMIN)만. OBSERVER·외부엔 버튼 미노출.
  const isStaffUp = ['ADMIN', 'MANAGER', 'STAFF'].includes(user?.role ?? '')
  const [noticeOpen, setNoticeOpen] = useState(false)

  const [clientType, setClientType] = useState('')
  const [region, setRegion] = useState('')
  const [clientId, setClientId] = useState('')
  const [expandedId, setExpandedId] = useState('') // 행 펼침(운수사) 드릴다운

  const filters = useMemo(
    () => ({
      client_type: clientType,
      region,
      client_id: clientId,
    }),
    [clientType, region, clientId],
  )

  const { data, isLoading, isError, refetch } = useSettlementSummary(filters)
  const rows = data?.items ?? []
  const total = data?.total ?? 0
  const totals = data?.totals
  const marketRateAvg6 = data?.market_rate_avg6 ?? null // 직전 6개월 평균시세(예상수익 기준, B2)

  async function handleExport() {
    if (exporting) return
    setExporting(true)
    try {
      await downloadExport('/asset-report/settlement-summary/export', filters, '자산관리보고.xlsx')
      showToast('엑셀 내보내기를 시작했습니다.', 'success')
    } catch (err) {
      showToast(err instanceof Error ? err.message : '내보내기에 실패했습니다.', 'danger')
    } finally {
      setExporting(false)
    }
  }

  const columns: Column<SettlementSummaryRow>[] = [
    {
      key: 'company_name',
      header: '운수사',
      className: 'min-w-[180px]',
      render: (v) => (
        <span className="font-semibold text-bone">{v.company_name ?? '미매칭'}</span>
      ),
    },
    {
      key: 'client_type',
      header: '구분',
      render: (v) => (
        <span className="text-sm text-ash">{v.client_type ? clientTypeLabel(v.client_type) : '—'}</span>
      ),
    },
    {
      key: 'region',
      header: '지역',
      render: (v) => <span className="text-sm text-ash">{v.region ?? '—'}</span>,
    },
    {
      key: 'participating_project_count',
      header: '참여사업수',
      className: 'text-right',
      render: (v) => <span className="text-sm text-bone">{fmtQty(v.participating_project_count)}</span>,
    },
    {
      key: 'participating_vehicle_count',
      header: '참여차량수',
      className: 'text-right',
      render: (v) => <span className="text-sm text-bone">{fmtQty(v.participating_vehicle_count)}</span>,
    },
    {
      key: 'total_reduction',
      header: '총감축량',
      className: 'text-right',
      render: (v) => <span className="text-sm text-ash"><Num value={v.total_reduction} unit="tCO₂" /></span>,
    },
    {
      key: 'effective_reduction',
      header: '잔여반영감축량',
      className: 'text-right',
      render: (v) => <span className="text-sm text-ash"><Num value={v.effective_reduction} unit="tCO₂" /></span>,
    },
    {
      key: 'expected_payout',
      header: '예상지급액(정산예정)',
      className: 'text-right',
      render: (v) => <MoneyCell value={v.expected_payout} />,
    },
    {
      key: 'expected_revenue',
      header: <span title="기준: 직전 6개월 평균시세">예상수익</span>,
      className: 'text-right',
      render: (v) => <MoneyCell value={v.expected_revenue ?? null} />,
    },
  ]

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="자산관리 보고"
        subtitle="운수사별 정산 예정 요약 — 고객사 단위 (cf. 재무 원장은 사업 단위)"
        actions={
          <div className="flex items-center gap-2">
            {/* 정산 통지 — 내부 실무자용(master.write). OBSERVER·외부엔 미노출 */}
            <RoleGate allow={isStaffUp}>
              <button
                type="button"
                onClick={() => setNoticeOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
              >
                <EnvelopeSimple size={16} />
                정산 통지
              </button>
            </RoleGate>
            <RoleGate allow={isManagerUp} reason="엑셀 내보내기는 팀장 이상만 가능합니다.">
              <button
                type="button"
                onClick={handleExport}
                disabled={exporting}
                className="inline-flex items-center gap-1.5 rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate disabled:cursor-not-allowed disabled:opacity-50"
              >
                <DownloadSimple size={16} />
                {exporting ? '내보내는 중…' : '엑셀 내보내기'}
              </button>
            </RoleGate>
          </div>
        }
      />

      <ScreenGuide
        perspective="운수사 단위"
        links={[
          { label: '사업 단위로', to: '/finance-ledger' },
          { label: '차량 단위로', to: '/asset-vehicles' },
          // 정산 관리(/settlements)는 OBSERVER 화이트리스트 밖 — 내부역할에게만 노출(깨진 링크 방지)
          ...(isObserver ? [] : [{ label: '정산 상태로', to: '/settlements' }]),
        ]}
      >
        각 운수사에 <strong className="font-medium text-bone">정산될 예정액</strong>을 운수사 단위로
        요약합니다(행 펼치면 사업별). 예상지급액은 전기버스 자산(차량)·재무 원장(사업)·자산관리 보고(운수사)
        에서 <strong className="font-medium text-bone">같은 값을 다른 축으로 본 것</strong>입니다.
      </ScreenGuide>

      {/* 전사 총계 KPI — 필터 기준 전 운수사 합 (사업수는 distinct, 금액 SensitiveData money) */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard
          title="참여 사업수"
          value={fmtQty(totals?.distinct_project_count)}
          sub="필터 기준 distinct 합"
          icon={<TreeStructure size={18} />}
          variant="dark"
        />
        <KpiCard
          title="참여 차량수"
          value={fmtQty(totals?.participating_vehicle_count)}
          sub="필터 기준 전 운수사 합"
          icon={<Truck size={18} />}
          variant="dark"
        />
        <KpiCard
          title="잔여반영감축량"
          value={<Num value={totals?.effective_reduction} unit="tCO₂" />}
          sub={<>총감축량 <Num value={totals?.total_reduction} unit="tCO₂" /></>}
          icon={<CheckCircle size={18} />}
          variant="dark"
        />
        <KpiCard
          title="예상지급액(정산예정)"
          value={<SensitiveData type="money" value={fmtMoney(totals?.expected_payout ?? null)} />}
          sub="필터 기준 전 운수사 합"
          icon={<Coins size={18} />}
          variant="dark"
        />
        <KpiCard
          title="예상수익"
          value={<SensitiveData type="money" value={fmtMoney(totals?.expected_revenue ?? null)} />}
          sub={`기준: 직전 6개월 평균시세 ${marketRateAvg6 != null ? `${marketRateAvg6.toLocaleString('ko-KR')} 원/tCO₂` : '-'}`}
          icon={<Coins size={18} />}
          variant="dark"
        />
      </div>

      <FilterBar>
        <FilterSelect
          label="구분"
          value={clientType}
          onChange={setClientType}
          options={clientTypeOptions}
        />
        <FilterSelect label="지역" value={region} onChange={setRegion} options={regionOptions} />
        {/* 운수사 필터는 /clients 의존 — OBSERVER는 차단 대상이라 숨김(훅도 enabled:false) */}
        {!isObserver && (
          <FilterSelect
            label="운수사"
            value={clientId}
            onChange={setClientId}
            options={clients.map((c) => ({ value: c.client_id, label: c.company_name }))}
          />
        )}
      </FilterBar>

      {isError ? (
        <EmptyState
          icon={<Coins size={36} />}
          title="정산 요약을 불러오지 못했습니다"
          description="네트워크 상태를 확인한 뒤 다시 시도해 주세요."
          action={
            <button
              type="button"
              onClick={() => refetch()}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
            >
              다시 시도
            </button>
          }
        />
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(v) => v.client_id ?? `unmatched:${v.company_name ?? ''}`}
          onRowClick={(v) => {
            const key = v.client_id ?? `unmatched:${v.company_name ?? ''}`
            setExpandedId((prev) => (prev === key ? '' : key))
          }}
          expandedKey={expandedId}
          renderExpanded={(v) => <ProjectBreakdownPanel row={v} />}
          isLoading={isLoading}
          emptyTitle="해당 조건의 운수사가 없습니다"
          emptyDescription="필터를 조정해 주세요."
        />
      )}

      {total > 0 && (
        <p className="px-1 text-xs text-slatey">총 {fmtQty(total)} 개 운수사</p>
      )}

      {/* 정산 통지 모달 — 게이트 통과(master.write) 시에만 마운트 */}
      {isStaffUp && noticeOpen && (
        <SettlementNoticeModal filters={filters} onClose={() => setNoticeOpen(false)} />
      )}
    </div>
  )
}

/** 정산 통지 모달 — 미리보기(대상·수신가능) → 확인 → 발송 → 건별 결과.
 *  현재 화면 필터를 그대로 대상 조건으로 사용한다(미매칭 운수사는 백엔드가 제외). */
function SettlementNoticeModal({
  filters,
  onClose,
}: {
  filters: SettlementSummaryFilters
  onClose: () => void
}) {
  const { showToast } = useToast()
  const preview = useSettlementNoticePreview()
  const send = useSettlementNoticeSend()

  const [confirmOpen, setConfirmOpen] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [result, setResult] = useState<SettlementNoticeSendResult | null>(null)
  // 통지 유형(P4) — 예정액/확정액. 기본 예정(무회귀). 확정 선택 시 대상=확정 header 보유 운수사만.
  const [noticeType, setNoticeType] = useState<SettlementNoticeType>('EXPECTED')
  // 통지 채널(P3) — 이메일/알림톡/둘 다. 기본 이메일(무회귀). 알림톡 미설정 시 알림톡 채널 발송 0.
  const [channel, setChannel] = useState<SettlementNoticeChannel>('EMAIL')

  // 통지 유형 변경 시 미리보기 재조회 — filters는 오픈 시점 스냅샷으로 고정.
  const { mutate: runPreview } = preview
  useEffect(() => {
    runPreview({ ...filters, notice_type: noticeType })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [noticeType])

  const data = preview.data
  const items = data?.items ?? []
  // 채널별 발송 가능 판정 — 이메일=수신자 & 예상지급액 산정, 알림톡=연동 번호 보유 & 예상지급액 산정.
  // 알림톡 본문엔 금액이 없으나 백엔드 sendable_alimtalk_count/alimtalk_sendable_ids가 payout not None을
  // 동일 게이트로 요구하므로('통지할 정산 존재' 불변식), 프론트 BOTH 카운트·sendableIds도 맞춰 과대집계를 막는다.
  const emailOk = (it: SettlementNoticePreviewItem) => it.can_receive && it.expected_payout != null
  const alimtalkOk = (it: SettlementNoticePreviewItem) =>
    !!it.can_receive_alimtalk && it.expected_payout != null
  const emailSendableCount = data?.sendable_count ?? 0
  const alimtalkSendableCount = data?.sendable_alimtalk_count ?? 0
  // BOTH는 적어도 한 채널 발송 가능한 운수사(합집합)를 로컬 집계
  const bothSendableCount = items.filter((it) => emailOk(it) || alimtalkOk(it)).length
  const channelSendableCount =
    channel === 'EMAIL'
      ? emailSendableCount
      : channel === 'ALIMTALK'
        ? alimtalkSendableCount
        : bothSendableCount
  // 알림톡 미설정/수신 불가 안내 — 대상은 있으나 알림톡 sendable이 0인 경우
  const alimtalkUnavailable = alimtalkSendableCount === 0 && (data?.total ?? 0) > 0
  // 미리보기에서 확정한 sendable client_id — 선택 채널 기준으로 send 대상 고정(표류 차단)
  const sendableIds = items
    .filter((it) =>
      channel === 'EMAIL'
        ? emailOk(it)
        : channel === 'ALIMTALK'
          ? alimtalkOk(it)
          : emailOk(it) || alimtalkOk(it),
    )
    .map((it) => it.client_id)

  async function handleSend() {
    try {
      const res = await send.mutateAsync({
        client_ids: sendableIds,
        subject: subject.trim() || undefined,
        body: body.trim() || undefined,
        notice_type: noticeType,
        channel,
      })
      setResult(res)
      setConfirmOpen(false)
      const parts = [`이메일 성공 ${res.sent}·실패 ${res.failed}`]
      if (channel !== 'EMAIL') {
        parts.push(`알림톡 성공 ${res.alimtalk_sent ?? 0}·실패 ${res.alimtalk_failed ?? 0}`)
      }
      showToast(
        `발송 완료 — ${parts.join(' · ')}`,
        res.failed > 0 || (res.alimtalk_failed ?? 0) > 0 ? 'danger' : 'success',
      )
    } catch (err) {
      // 503(Gmail 미설정)·기타 — 서버 detail 우선 안내(발송 안 됨)
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      showToast(detail ?? '이메일 발송이 설정되지 않았습니다(환경설정 > 연동).', 'danger')
      setConfirmOpen(false)
    }
  }

  return (
    <>
      <Modal
        open
        onClose={onClose}
        title="정산 통지 메일"
        size="lg"
        footer={
          result ? (
            <button
              type="button"
              onClick={onClose}
              className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-on-primary hover:opacity-90"
            >
              닫기
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={onClose}
                className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
              >
                취소
              </button>
              <button
                type="button"
                onClick={() => setConfirmOpen(true)}
                disabled={preview.isPending || channelSendableCount === 0}
                className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-on-primary hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                발송 ({channelSendableCount})
              </button>
            </>
          )
        }
      >
        {result ? (
          <NoticeResultView result={result} />
        ) : (
          <div className="space-y-3">
            {/* 통지 유형 토글 — 예정액 통지 / 확정액 통지. 확정은 확정 header 보유 운수사만(백엔드 필터) */}
            <div className="flex gap-1.5 rounded-full border border-hairline bg-elevate p-1 text-sm">
              {(['EXPECTED', 'CONFIRMED'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setNoticeType(t)}
                  disabled={preview.isPending}
                  className={`flex-1 rounded-full px-3 py-1.5 font-medium transition disabled:opacity-60 ${
                    noticeType === t ? 'bg-primary text-on-primary' : 'text-slatey hover:text-bone'
                  }`}
                >
                  {t === 'EXPECTED' ? '예정액 통지' : '확정액 통지'}
                </button>
              ))}
            </div>
            {/* 통지 채널 토글 — 이메일 / 알림톡 / 둘 다. 알림톡은 금액 미포함(도착 알림+링크) */}
            <div className="flex gap-1.5 rounded-full border border-hairline bg-elevate p-1 text-sm">
              {(['EMAIL', 'ALIMTALK', 'BOTH'] as const).map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setChannel(c)}
                  disabled={preview.isPending}
                  className={`flex-1 rounded-full px-3 py-1.5 font-medium transition disabled:opacity-60 ${
                    channel === c ? 'bg-primary text-on-primary' : 'text-slatey hover:text-bone'
                  }`}
                >
                  {c === 'EMAIL' ? '이메일' : c === 'ALIMTALK' ? '알림톡' : '이메일+알림톡'}
                </button>
              ))}
            </div>
            {preview.isPending ? (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-slatey">
            <CircleNotch size={18} className="animate-spin" />
            대상을 확인하는 중…
          </div>
        ) : preview.isError ? (
          <p className="py-6 text-center text-sm text-rose-400">
            대상을 불러오지 못했습니다. 다시 시도해 주세요.
          </p>
        ) : items.length === 0 ? (
          <p className="py-6 text-center text-sm text-slatey">
            {noticeType === 'CONFIRMED'
              ? '확정된 정산이 있는 운수사가 없습니다. (미확정·미지정 운수사는 제외됩니다.)'
              : '통지 대상 운수사가 없습니다. (미지정 운수사는 제외됩니다.)'}
          </p>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-ash">
              대상 <b className="text-bone">{items.length}</b>개사 중 이메일 발송 가능{' '}
              <b className="text-emerald-400">{emailSendableCount}</b>개사 · 알림톡 발송 가능{' '}
              <b className="text-emerald-400">{alimtalkSendableCount}</b>개사
              <span className="text-slatey"> · 수신자 없는 운수사는 발송에서 제외됩니다.</span>
            </p>

            {/* 알림톡 미설정/수신 불가 안내 — 알림톡 포함 채널 선택 시 노출 */}
            {alimtalkUnavailable && channel !== 'EMAIL' && (
              <p className="rounded-xl border border-amber-400/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
                카카오 알림톡이 아직 설정되지 않았거나 수신 가능한 운수사가 없습니다(환경설정 &gt; 연동).
                {channel === 'ALIMTALK'
                  ? ' 알림톡 단독 발송은 할 수 없습니다.'
                  : ' 이메일 수신자에게만 발송됩니다.'}
              </p>
            )}

            <div className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
              {items.map((item) => (
                <div
                  key={item.client_id}
                  className="flex items-center gap-2 rounded-xl border border-hairline bg-elevate px-3 py-2"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-bone">{item.company_name}</p>
                    <p className="text-xs text-slatey">
                      참여사업 {fmtQty(item.participating_project_count)} · 참여차량{' '}
                      {fmtQty(item.participating_vehicle_count)}
                      {item.can_receive && ` · 이메일 ${fmtQty(item.to_count)}명`}
                      {item.can_receive_alimtalk && ` · 알림톡 ${fmtQty(item.alimtalk_to_count)}명`}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <MoneyCell value={item.expected_payout ?? null} />
                  </div>
                  {/* 채널별 수신 가능 배지 — 이메일/알림톡 병기 */}
                  {item.can_receive && (
                    <span
                      className="inline-flex shrink-0 items-center gap-1 rounded-full border border-emerald-400/25 bg-emerald-500/15 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300"
                      title="공통 수신자 또는 주 담당자 이메일로 발송됩니다"
                    >
                      <EnvelopeSimple size={11} weight="fill" />
                      이메일
                    </span>
                  )}
                  {item.can_receive_alimtalk && (
                    <span
                      className="inline-flex shrink-0 items-center gap-1 rounded-full border border-emerald-400/25 bg-emerald-500/15 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300"
                      title="카카오 알림톡 연동 번호로 발송됩니다(금액 미포함, 도착 알림+링크)"
                    >
                      <ChatCircleDots size={11} weight="fill" />
                      알림톡
                    </span>
                  )}
                  {!item.can_receive && !item.can_receive_alimtalk && (
                    <span
                      className="inline-flex shrink-0 items-center gap-1 rounded-full border border-amber-400/25 bg-amber-500/15 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:text-amber-300"
                      title="공통 수신자 또는 주 담당자 이메일·알림톡 번호가 없어 발송이 제외됩니다"
                    >
                      <WarningCircle size={11} weight="fill" />
                      수신자 없음
                    </span>
                  )}
                </div>
              ))}
            </div>

            {/* 고급 옵션 — 제목/본문 오버라이드(미지정 시 기본 템플릿) */}
            <div className="border-t border-hairline pt-2">
              <button
                type="button"
                onClick={() => setShowAdvanced((v) => !v)}
                className="text-xs font-medium text-slatey hover:text-bone"
              >
                {showAdvanced ? '▾ 고급 옵션 닫기' : '▸ 고급 옵션 (제목·본문 직접 입력)'}
              </button>
              {showAdvanced && (
                <div className="mt-2 space-y-2">
                  <input
                    type="text"
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    placeholder="제목 (미입력 시 기본 템플릿)"
                    className="w-full rounded-xl border border-hairline bg-elevate px-3 py-2 text-sm text-bone placeholder:text-smoke"
                  />
                  <textarea
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    placeholder="본문 (미입력 시 기본 템플릿)"
                    rows={3}
                    className="w-full rounded-xl border border-hairline bg-elevate px-3 py-2 text-sm text-bone placeholder:text-smoke"
                  />
                </div>
              )}
            </div>
          </div>
            )}
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={confirmOpen}
        title="정산 통지 발송"
        message={
          <>
            <b className="text-bone">{channelSendableCount}</b>개사에 정산{' '}
            {noticeType === 'CONFIRMED' ? '확정액' : '예정액'} 통지를{' '}
            {channel === 'EMAIL' ? '이메일' : channel === 'ALIMTALK' ? '카카오 알림톡' : '이메일·알림톡'}
            (으)로 보냅니다.
            <br />
            발송 후에는 되돌릴 수 없습니다.
          </>
        }
        confirmLabel="발송"
        danger
        loading={send.isPending}
        onConfirm={handleSend}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  )
}

/** 채널별 결과 배지 — SENT=성공(초록)/FAILED=실패(빨강)/SKIPPED=스킵(중립 회색). 채널 아이콘 병기 */
function ChannelBadge({
  icon,
  label,
  state,
}: {
  icon: ReactNode
  label: string
  state: 'SENT' | 'FAILED' | 'SKIPPED'
}) {
  const tone =
    state === 'SENT'
      ? 'border-emerald-400/25 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
      : state === 'SKIPPED'
        ? 'border-hairline bg-elevate text-ash'
        : 'border-rose-400/25 bg-rose-500/15 text-rose-700 dark:text-rose-300'
  const suffix = state === 'SENT' ? '성공' : state === 'SKIPPED' ? '스킵' : '실패'
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${tone}`}
    >
      {icon}
      {label} {suffix}
    </span>
  )
}

/** 발송 결과 요약 — 이메일·알림톡 성공/실패 + 건별 채널 결과(email_result/alimtalk_result, 없으면 result) */
function NoticeResultView({ result }: { result: SettlementNoticeSendResult }) {
  const alimtalkSent = result.alimtalk_sent ?? 0
  const alimtalkFailed = result.alimtalk_failed ?? 0
  const hasAlimtalk =
    alimtalkSent > 0 ||
    alimtalkFailed > 0 ||
    result.details.some((d) => d.alimtalk_result != null)
  return (
    <div className="space-y-3">
      <p className="text-sm text-ash">
        대상 <b className="text-bone">{result.target_count}</b> · 이메일 성공{' '}
        <span className="text-emerald-400">{result.sent}</span> 실패{' '}
        <span className={result.failed > 0 ? 'text-rose-400' : ''}>{result.failed}</span>
        {hasAlimtalk && (
          <>
            {' '}
            · 알림톡 성공 <span className="text-emerald-400">{alimtalkSent}</span> 실패{' '}
            <span className={alimtalkFailed > 0 ? 'text-rose-400' : ''}>{alimtalkFailed}</span>
          </>
        )}
      </p>
      <div className="max-h-72 space-y-1.5 overflow-y-auto pr-1">
        {result.details.map((d) => (
          <div
            key={d.client_id}
            className="flex items-center gap-2 rounded-xl border border-hairline bg-elevate px-3 py-2"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-bone">{d.company_name}</p>
              {d.result === 'FAILED' && d.reason && (
                <p className="truncate text-xs text-rose-400" title={d.reason}>
                  {d.reason}
                </p>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {/* 채널별 결과가 있으면 채널 배지 병기, 없으면 통합 결과 배지 */}
              {d.email_result != null || d.alimtalk_result != null ? (
                <>
                  {d.email_result != null && (
                    <ChannelBadge
                      icon={<EnvelopeSimple size={11} weight="fill" />}
                      label="이메일"
                      state={d.email_result}
                    />
                  )}
                  {d.alimtalk_result != null && (
                    <ChannelBadge
                      icon={<ChatCircleDots size={11} weight="fill" />}
                      label="알림톡"
                      state={d.alimtalk_result}
                    />
                  )}
                </>
              ) : d.result === 'SENT' ? (
                <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-emerald-400/25 bg-emerald-500/15 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300">
                  <CheckCircle size={11} weight="fill" />
                  성공
                </span>
              ) : (
                <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-rose-400/25 bg-rose-500/15 px-2 py-0.5 text-[11px] font-semibold text-rose-700 dark:text-rose-300">
                  <WarningCircle size={11} weight="fill" />
                  실패
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/** 행 펼침 상세 — 해당 운수사가 참여한 사업별 브레이크다운(사업명·차량수·감축량·예상지급액) */
function ProjectBreakdownPanel({ row }: { row: SettlementSummaryRow }) {
  if (row.projects.length === 0) {
    return <p className="text-sm text-slatey">참여 사업 내역이 없습니다.</p>
  }
  return (
    <div className="space-y-2 text-sm">
      <h4 className="text-xs font-semibold tracking-wide text-ash">참여 사업 내역</h4>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse">
          <thead>
            <tr className="border-b border-hairline text-left text-xs text-slatey">
              <th className="py-1.5 pr-4 font-medium">사업명</th>
              <th className="py-1.5 pr-4 text-right font-medium">차량수</th>
              <th className="py-1.5 pr-4 text-right font-medium">총감축량</th>
              <th className="py-1.5 pr-4 text-right font-medium">잔여반영감축량</th>
              <th className="py-1.5 pr-4 text-right font-medium">예상지급액</th>
              <th className="py-1.5 text-right font-medium" title="기준: 직전 6개월 평균시세">
                예상수익
              </th>
            </tr>
          </thead>
          <tbody>
            {row.projects.map((p) => (
              <tr key={p.project_id} className="border-b border-hairline/60">
                <td className="py-1.5 pr-4 text-bone">{p.project_name ?? '—'}</td>
                <td className="py-1.5 pr-4 text-right text-ash">{fmtQty(p.vehicle_count)}</td>
                <td className="py-1.5 pr-4 text-right text-ash"><Num value={p.total_reduction} unit="tCO₂" /></td>
                <td className="py-1.5 pr-4 text-right text-ash">
                  <Num value={p.effective_reduction} unit="tCO₂" />
                </td>
                <td className="py-1.5 pr-4 text-right">
                  <MoneyCell value={p.expected_payout} />
                </td>
                <td className="py-1.5 text-right">
                  <MoneyCell value={p.expected_revenue ?? null} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
