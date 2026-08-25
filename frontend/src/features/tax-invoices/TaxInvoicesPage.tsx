// 세금계산서 원장 — 홈택스 보안메일 HTML 자동반영(업로드→미리보기→적용) + 원장 조회
import { useMemo, useState } from 'react'
import { SectionTabs } from '../../components/SectionTabs'
import { PageHeader } from '../../components/PageHeader'
import { useToast } from '../../components/Toast'
import { useAuth } from '../../app/AuthProvider'
import { TaxSummaryPanel } from './TaxSummaryPanel'
import { TaxIntegrityPanel } from './TaxIntegrityPanel'
import { TaxBreakdownPanel } from './TaxBreakdownPanel'
import {
  useCommitScan,
  useCommitTaxInvoices,
  usePreviewScan,
  usePreviewTaxInvoices,
  useRematchTaxInvoices,
  useTaxInvoices,
} from './api'
import type { TaxInvoicePreviewItem } from './types'

const won = (v?: number | null) =>
  v === null || v === undefined ? '—' : `${v.toLocaleString('ko-KR')}원`

function DirBadge({ d }: { d?: string | null }) {
  const cls =
    d === '매입'
      ? 'bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-400/25'
      : d === '매출'
        ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-400/25'
        : 'bg-elevate-strong text-ash border-hairline'
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${cls}`}>
      {d ?? '미상'}
    </span>
  )
}

const REASON_LABEL: Record<string, string> = {
  password_unresolved: '복호화 실패(사업자번호 미보유)',
  header_missing: '보안메일 형식 아님',
  header_decode_error: '헤더 해독 오류',
  decrypt_or_parse_error: '복호화/파싱 오류',
  no_approval_no: '승인번호 없음',
}

function matchLabel(it: TaxInvoicePreviewItem): string {
  if (it.matched_client_name) return `운수사: ${it.matched_client_name}`
  if (it.matched_buyer_name) return `투자사: ${it.matched_buyer_name}`
  return '미매칭'
}

export function TaxInvoicesPage() {
  const { showToast } = useToast()
  const { user } = useAuth()
  // 적재(업로드·적용)는 쓰기 권한(master.write=STAFF↑)만. 경영전략실 등 읽기 역할은 조회·집계만.
  const canWrite = !!user && ['ADMIN', 'MANAGER', 'STAFF'].includes(user.role)
  // 요약(경영전략실 기본) / 원장 내부 탭
  const [tab, setTab] = useState<'summary' | 'integrity' | 'breakdown' | 'ledger'>('summary')
  const [files, setFiles] = useState<File[]>([])
  const [preview, setPreview] = useState<TaxInvoicePreviewItem[] | null>(null)
  const [source, setSource] = useState<'upload' | 'scan'>('upload')
  const [scanFolder, setScanFolder] = useState('')

  const previewM = usePreviewTaxInvoices()
  const commitM = useCommitTaxInvoices()
  const previewScanM = usePreviewScan()
  const commitScanM = useCommitScan()
  const rematchM = useRematchTaxInvoices()
  const committing = commitM.isPending || commitScanM.isPending

  const onRematch = async () => {
    try {
      const r = await rematchM.mutateAsync()
      showToast(
        `재매칭 — 운수사 ${r.relinked_client}·투자사 ${r.relinked_buyer} 연결${r.still_unmatched > 0 ? ` · 미매칭 ${r.still_unmatched}건(마스터 미등록)` : ''}`,
        r.relinked_client + r.relinked_buyer > 0 ? 'success' : 'info',
      )
    } catch (e) {
      showErr(e, '재매칭에 실패했습니다.')
    }
  }

  // 원장 조회
  const [direction, setDirection] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 50
  const { data: ledger, isLoading } = useTaxInvoices({
    direction: direction || undefined,
    search: search.trim() || undefined,
    page,
    page_size: pageSize,
  })

  const applicable = useMemo(
    () => (preview ?? []).filter((i) => i.ok && !i.is_duplicate).length,
    [preview],
  )

  const showErr = (e: unknown, fallback: string) => {
    const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    showToast(detail ?? fallback, 'danger')
  }

  const onSelectFiles = async (selected: FileList | null) => {
    if (!selected || selected.length === 0) return
    const arr = Array.from(selected)
    setFiles(arr)
    setSource('upload')
    setPreview(null)
    try {
      const res = await previewM.mutateAsync(arr)
      setPreview(res.items)
    } catch (e) {
      showErr(e, '미리보기에 실패했습니다.')
    }
  }

  const onScan = async () => {
    setSource('scan')
    setFiles([])
    setPreview(null)
    try {
      const res = await previewScanM.mutateAsync(scanFolder.trim())
      setPreview(res.items)
      if (res.items.length === 0) showToast('폴더에서 HTML을 찾지 못했습니다.', 'info')
    } catch (e) {
      showErr(e, '폴더 스캔에 실패했습니다.')
    }
  }

  const onCommit = async () => {
    if (!preview || applicable === 0) return
    if (!window.confirm(`적용 대상 ${applicable}건을 세금계산서 원장에 반영합니다. 진행할까요?`)) return
    try {
      const r =
        source === 'scan'
          ? await commitScanM.mutateAsync(scanFolder.trim())
          : await commitM.mutateAsync(files)
      const kind = r.held > 0 ? 'danger' : r.duplicate > 0 ? 'info' : 'success'
      showToast(
        `적용 완료 — 생성 ${r.created} · 중복 ${r.duplicate} · 보류 ${r.held} (총 ${r.total})`,
        kind,
      )
      setFiles([])
      setPreview(null)
    } catch (e) {
      showErr(e, '적용에 실패했습니다.')
    }
  }

  const total = ledger?.total ?? 0
  const maxPage = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="space-y-6">
      {/* 허브 서브탭(A안) — 재무/자산 묶음 화면 전환 */}
      <SectionTabs />
      <PageHeader title="세금계산서 관리" subtitle="매입·매출 요약 + 원장(홈택스 보안메일 HTML 자동반영)" />

      {/* 요약 / 원장 탭 — 경영전략실은 요약 기본 */}
      <div className="flex w-fit items-center gap-1 rounded-full border border-hairline bg-elevate p-0.5">
        {(
          [
            { key: 'summary', label: '요약' },
            { key: 'integrity', label: '정합성' },
            { key: 'breakdown', label: '집계' },
            { key: 'ledger', label: '원장' },
          ] as const
        ).map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`rounded-full px-4 py-1.5 text-xs font-semibold transition-colors ${
              tab === t.key ? 'bg-elevate-strong text-bone' : 'text-slatey hover:text-ash'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'summary' && <TaxSummaryPanel />}
      {tab === 'integrity' && <TaxIntegrityPanel />}
      {tab === 'breakdown' && <TaxBreakdownPanel />}

      {tab === 'ledger' && (
        <>
      {/* 적재(업로드·미리보기·적용) — 쓰기 권한자 전용. 읽기 역할은 원장 조회만 노출 */}
      {canWrite && (
        <>
      {/* 업로드 */}
      <section className="rounded-2xl border border-hairline bg-graphite p-5">
        <p className="text-sm font-semibold text-bone">HTML 업로드</p>
        <p className="mt-1 text-xs leading-relaxed text-slatey">
          국세청 홈택스 전자세금계산서 보안메일(.html)을 여러 개 선택하면 사업자번호로 자동
          복호화해 미리보기를 만듭니다. 자사 사업자번호는 환경설정 &gt; 시스템설정의
          <code className="mx-1 rounded bg-elevate-strong px-1 py-0.5 font-mono text-[11px]">company_biz_reg_no</code>
          (복수 시 콤마로 구분)에 등록하세요.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label className="cursor-pointer rounded-full border border-hairline bg-elevate px-4 py-2 text-sm font-medium text-bone hover:border-red-600/60 dark:hover:border-red-500/60">
            HTML 파일 선택
            <input
              type="file"
              accept=".html,text/html"
              multiple
              className="hidden"
              onChange={(e) => onSelectFiles(e.target.files)}
            />
          </label>
          {files.length > 0 && (
            <span className="text-xs text-ash">{files.length}개 선택됨</span>
          )}
          {previewM.isPending && <span className="text-xs text-slatey">미리보기 생성 중…</span>}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-hairline pt-3">
          <span className="text-xs font-medium text-ash">또는 Dropbox 정산 폴더 스캔:</span>
          <input
            value={scanFolder}
            onChange={(e) => setScanFolder(e.target.value)}
            placeholder="/세금계산서 (비우면 기본 폴더)"
            className="h-9 w-64 rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
          />
          <button
            type="button"
            onClick={onScan}
            disabled={previewScanM.isPending}
            className="rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate disabled:opacity-50"
          >
            {previewScanM.isPending ? '스캔 중…' : '폴더 스캔'}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-hairline pt-3">
          <span className="text-xs font-medium text-ash">미매칭 재매칭:</span>
          <button
            type="button"
            onClick={onRematch}
            disabled={rematchM.isPending}
            className="rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate disabled:opacity-50"
          >
            {rematchM.isPending ? '재매칭 중…' : '미매칭 재매칭'}
          </button>
          <span className="text-[11px] text-slatey">고객사·투자사를 나중에 등록했다면 눌러 상대 사업자번호로 자동 연결(재업로드 불필요).</span>
        </div>
      </section>

      {/* 미리보기 */}
      {preview && (
        <section className="rounded-2xl border border-hairline bg-graphite p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold text-bone">
              미리보기 · 적용대상 {applicable} / 총 {preview.length}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  setFiles([])
                  setPreview(null)
                }}
                className="rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate"
              >
                지우기
              </button>
              <button
                type="button"
                onClick={onCommit}
                disabled={applicable === 0 || committing}
                className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {committing ? '적용 중…' : `적용 ${applicable}건`}
              </button>
            </div>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-sm">
              <thead className="border-b border-hairline text-[11px] uppercase tracking-wider text-slatey">
                <tr>
                  <th className="px-2 py-2">파일</th>
                  <th className="px-2 py-2">방향</th>
                  <th className="px-2 py-2">상대(상호/번호)</th>
                  <th className="px-2 py-2 text-right">공급가액</th>
                  <th className="px-2 py-2">작성일</th>
                  <th className="px-2 py-2">매칭</th>
                  <th className="px-2 py-2">상태</th>
                </tr>
              </thead>
              <tbody>
                {preview.map((it, i) => (
                  <tr key={i} className="border-b border-hairline/60">
                    <td className="max-w-[160px] truncate px-2 py-2 text-ash" title={it.filename ?? ''}>
                      {it.filename}
                    </td>
                    <td className="px-2 py-2">{it.ok ? <DirBadge d={it.direction} /> : '—'}</td>
                    <td className="px-2 py-2 text-bone">
                      {it.ok ? (
                        <span>
                          {it.counterpart_name ?? '—'}
                          <span className="ml-1 font-mono text-[11px] text-slatey">
                            {it.counterpart_reg_no}
                          </span>
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-2 py-2 text-right font-medium text-bone">
                      {it.ok ? won(it.supply_amount) : '—'}
                    </td>
                    <td className="px-2 py-2 text-ash">{it.issue_date ?? '—'}</td>
                    <td className="px-2 py-2 text-ash">{it.ok ? matchLabel(it) : '—'}</td>
                    <td className="px-2 py-2">
                      {!it.ok ? (
                        <span className="text-rose-500">
                          보류 · {REASON_LABEL[it.reason ?? ''] ?? it.reason}
                        </span>
                      ) : it.is_duplicate ? (
                        <span className="text-amber-600 dark:text-amber-400">이미 반영됨</span>
                      ) : (
                        <span className="text-emerald-600 dark:text-emerald-400">신규</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
        </>
      )}

      {/* 원장 목록 */}
      <section className="rounded-2xl border border-hairline bg-graphite p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-semibold text-bone">원장 ({total})</p>
          <div className="flex flex-wrap gap-2">
            <select
              value={direction}
              onChange={(e) => {
                setDirection(e.target.value)
                setPage(1)
              }}
              className="h-9 rounded-lg border border-hairline bg-graphite px-2.5 text-sm text-bone focus:border-white/30 focus:outline-none"
            >
              <option value="">전체 방향</option>
              <option value="매입">매입</option>
              <option value="매출">매출</option>
              <option value="미상">미상</option>
            </select>
            <input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
              placeholder="상대 상호·사업자번호"
              className="h-9 w-52 rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
            />
          </div>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="border-b border-hairline text-[11px] uppercase tracking-wider text-slatey">
              <tr>
                <th className="px-2 py-2">작성일</th>
                <th className="px-2 py-2">방향</th>
                <th className="px-2 py-2">공급자 → 받는자</th>
                <th className="px-2 py-2">상대</th>
                <th className="px-2 py-2 text-right">공급가액</th>
                <th className="px-2 py-2 text-right">세액</th>
                <th className="px-2 py-2 text-right">합계</th>
                <th className="px-2 py-2">승인번호</th>
              </tr>
            </thead>
            <tbody>
              {(ledger?.items ?? []).map((r) => (
                <tr key={r.tax_invoice_id} className="border-b border-hairline/60">
                  <td className="px-2 py-2 text-ash">{r.issue_date ?? '—'}</td>
                  <td className="px-2 py-2">
                    <DirBadge d={r.direction} />
                  </td>
                  <td className="px-2 py-2 text-bone">
                    {r.invoicer_name ?? r.invoicer_reg_no} → {r.invoicee_name ?? r.invoicee_reg_no}
                  </td>
                  <td className="px-2 py-2 text-ash">
                    {r.counterpart_name ?? '—'}
                    <span className="ml-1 font-mono text-[11px] text-slatey">
                      {r.counterpart_reg_no}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-right font-medium text-bone">{won(r.supply_amount)}</td>
                  <td className="px-2 py-2 text-right text-ash">{won(r.tax_amount)}</td>
                  <td className="px-2 py-2 text-right text-ash">{won(r.total_amount)}</td>
                  <td className="px-2 py-2 font-mono text-[11px] text-slatey">{r.approval_no}</td>
                </tr>
              ))}
              {!isLoading && (ledger?.items ?? []).length === 0 && (
                <tr>
                  <td colSpan={8} className="px-2 py-8 text-center text-sm text-slatey">
                    적재된 세금계산서가 없습니다. 위에서 HTML을 업로드하세요.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {maxPage > 1 && (
          <div className="mt-3 flex items-center justify-end gap-2 text-sm">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded-lg border border-hairline px-3 py-1.5 text-bone hover:bg-elevate disabled:opacity-40"
            >
              이전
            </button>
            <span className="text-ash">
              {page} / {maxPage}
            </span>
            <button
              type="button"
              disabled={page >= maxPage}
              onClick={() => setPage((p) => Math.min(maxPage, p + 1))}
              className="rounded-lg border border-hairline px-3 py-1.5 text-bone hover:bg-elevate disabled:opacity-40"
            >
              다음
            </button>
          </div>
        )}
      </section>
        </>
      )}
    </div>
  )
}
