// 세그먼트 발송 (SCR-12 확장) — 조건 빌더(좌) + 실시간 미리보기(우) 단일 화면
// 축 간 AND, 축 내 IN(OR). 조건 변경 300ms 디바운스 후 POST /segments/preview.
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowCounterClockwise,
  BookmarkSimple,
  Buildings,
  CaretDown,
  CaretRight,
  CheckSquare,
  CircleNotch,
  FileText,
  FloppyDisk,
  Funnel,
  PaperPlaneRight,
  Square,
  WarningCircle,
  X,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { EmptyState } from '../../components/EmptyState'
import { Modal } from '../../components/Modal'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { DropboxPicker } from '../../components/DropboxPicker'
import { StatusBadge } from '../../components/StatusBadge'
import { FilterSearch } from '../../components/FilterBar'
import { useToast } from '../../components/Toast'
import { api } from '../../lib/api/client'
import { unwrapList, useCodes } from '../../lib/api/queries'
import { useDebounced } from '../../lib/useDebounced'
import { fmtServerDateTime } from '../../lib/format'
import { docTypeLabel } from '../documents/DocumentsPage'
import { useProjectOptions } from '../projects/api'
import type {
  Document,
  Paginated,
  Segment,
  SegmentCriteria,
  SegmentSendResponse,
} from '../../types'
import {
  useDeleteSegment,
  useSaveSegment,
  useSegmentFacets,
  useSegmentPreview,
  useSegmentSendDetail,
  useSegmentSends,
  useSegments,
  useSendSegment,
} from './api'

type AxisKey = keyof SegmentCriteria

const AXIS_LABELS: Record<AxisKey, string> = {
  region: '지역',
  client_type: '구분',
  contract_status: '계약 상태',
  project_id: '감축 사업',
  asset_group: '자산 대분류',
  settlement_status: '정산 상태',
}

// 세그먼트용 기본 메일 문구 — 월간 템플릿의 {보고서유형}은 세그먼트 발송에서
// 치환되지 않으므로 사용 금지. 사용 가능 변수: {고객사명} {연도} {월} {담당자명}
const DEFAULT_SUBJECT = '[Hooxi] {고객사명} 안내 자료 송부'
const DEFAULT_BODY = `{고객사명} 담당자님, 안녕하세요.
후시파트너스입니다.

{연도}년 {월}월 안내 자료를 첨부와 같이 송부드립니다.
확인 부탁드리며, 문의 사항은 본 메일로 회신 주시기 바랍니다.

감사합니다.
{담당자명} 드림`

export function SegmentsPage() {
  const [criteria, setCriteria] = useState<SegmentCriteria>({})
  const debouncedCriteria = useDebounced(criteria, 300)

  // 축 선택지 — region은 서버 facets, 코드 축은 공통 코드 마스터, 사업은 목록 API 재사용
  const { data: facets } = useSegmentFacets()
  const { data: projects = [] } = useProjectOptions()
  const clientType = useCodes('CLIENT_TYPE')
  const contractStatus = useCodes('CONTRACT_STATUS')
  const assetGroup = useCodes('ASSET_GROUP')
  const settlementStatus = useCodes('SETTLEMENT_STATUS')
  const clientFolderCodes = useCodes('CLIENT_FOLDER') // mail-merge 구분폴더 선택지

  const projectNameOf = useMemo(() => {
    const m: Record<string, string> = {}
    for (const p of projects) m[p.project_id] = p.project_name
    return (id: string) => m[id] ?? id
  }, [projects])

  // 축 정의 — 옵션 목록 + 값→표시명 (칩 라벨용)
  const axes: {
    key: AxisKey
    options: { value: string; label: string }[]
    labelOf: (value: string) => string
  }[] = [
    {
      key: 'region',
      options: (facets?.regions ?? []).map((r) => ({ value: r, label: r })),
      labelOf: (v) => v,
    },
    { key: 'client_type', options: clientType.options, labelOf: clientType.labelOf },
    {
      key: 'contract_status',
      options: contractStatus.options,
      labelOf: contractStatus.labelOf,
    },
    {
      key: 'project_id',
      options: projects.map((p) => ({ value: p.project_id, label: p.project_name })),
      labelOf: projectNameOf,
    },
    { key: 'asset_group', options: assetGroup.options, labelOf: assetGroup.labelOf },
    {
      key: 'settlement_status',
      options: settlementStatus.options,
      labelOf: settlementStatus.labelOf,
    },
  ]

  const hasCriteria = useMemo(
    () => Object.values(criteria).some((values) => (values?.length ?? 0) > 0),
    [criteria],
  )

  // 조건을 손대면 저장 세그먼트 선택 해제 — 발송이 저장분(criteria)과 어긋나지 않게
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null)

  const addValue = (key: AxisKey, value: string) => {
    setSelectedSegmentId(null)
    setCriteria((prev) => {
      const current = prev[key] ?? []
      if (current.includes(value)) return prev
      return { ...prev, [key]: [...current, value] }
    })
  }

  const removeValue = (key: AxisKey, value: string) => {
    setSelectedSegmentId(null)
    setCriteria((prev) => {
      const next = (prev[key] ?? []).filter((v) => v !== value)
      const copy = { ...prev }
      if (next.length > 0) copy[key] = next
      else delete copy[key]
      return copy
    })
  }

  const resetCriteria = () => {
    setSelectedSegmentId(null)
    setCriteria({})
  }

  // 실시간 미리보기 — 디바운스된 조건으로 조회 (placeholderData로 깜빡임 방지)
  const preview = useSegmentPreview(debouncedCriteria)
  const previewItems = preview.data?.items ?? []
  const receivable = previewItems.filter((i) => i.can_receive).length
  const targetTotal = preview.data?.total ?? 0
  // 종료(END) 계약 고객사 수 — 발송 확인 시 오발송 경고용
  const endedCount = previewItems.filter((i) => i.contract_status === 'END').length

  // ── 발송 구성 — 첨부 문서(문서함 픽커) + 제목/본문 + 확인 다이얼로그 ──
  const { showToast } = useToast()
  const [attachedDocs, setAttachedDocs] = useState<Document[]>([])
  const [pickerOpen, setPickerOpen] = useState(false)
  const [dropboxPaths, setDropboxPaths] = useState<string[]>([])
  const [dbxPickerOpen, setDbxPickerOpen] = useState(false)
  const [mergeFolderCode, setMergeFolderCode] = useState('') // mail-merge 구분폴더(빈값=미사용)
  const [mergeNameContains, setMergeNameContains] = useState('')
  const [subject, setSubject] = useState(DEFAULT_SUBJECT)
  const [body, setBody] = useState(DEFAULT_BODY)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [lastResult, setLastResult] = useState<SegmentSendResponse | null>(null)
  const send = useSendSegment()

  const toggleDoc = (doc: Document) => {
    setAttachedDocs((prev) =>
      prev.some((d) => d.doc_id === doc.doc_id)
        ? prev.filter((d) => d.doc_id !== doc.doc_id)
        : [...prev, doc],
    )
  }

  const canSend =
    (attachedDocs.length > 0 || dropboxPaths.length > 0 || !!mergeFolderCode) &&
    targetTotal > 0 &&
    !send.isPending

  const handleSend = async () => {
    try {
      // 저장 세그먼트 선택 중(조건 미수정)이면 /segments/{id}/send — 이력에 segment_id 연결
      const res = await send.mutateAsync({
        segmentId: selectedSegmentId ?? undefined,
        payload: {
          doc_ids: attachedDocs.map((d) => d.doc_id),
          dropbox_paths: dropboxPaths.length ? dropboxPaths : undefined,
          merge_folder_code: mergeFolderCode || undefined,
          merge_name_contains: mergeNameContains.trim() || undefined,
          subject: subject.trim() || undefined,
          body: body.trim() || undefined,
          ...(selectedSegmentId ? {} : { criteria }), // 즉석 발송 — 현재 조건 스냅샷
        },
      })
      setLastResult(res)
      setConfirmOpen(false)
      showToast(
        `발송 완료 — 성공 ${res.sent_count}건, 실패 ${res.failed_count}건`,
        res.failed_count > 0 ? 'danger' : 'success',
      )
    } catch (err) {
      // 503(Gmail 미설정)·404·422 등 — 서버 detail 우선 안내
      const detail = (err as { response?: { data?: { detail?: string } } })?.response
        ?.data?.detail
      showToast(detail ?? '발송에 실패했습니다.', 'danger')
      setConfirmOpen(false)
    }
  }

  // ── 저장된 세그먼트 — 칩 클릭으로 조건 로드, 현재 조합 저장/삭제 ──────
  const { data: segments = [] } = useSegments()
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [saveDesc, setSaveDesc] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Segment | null>(null)
  const saveSegment = useSaveSegment()
  const deleteSegment = useDeleteSegment()

  const loadSegment = (s: Segment) => {
    setCriteria(s.criteria ?? {})
    setSelectedSegmentId(s.segment_id)
    // 세그먼트 기본 메일 템플릿이 있으면 반영 (없으면 현재 입력 유지)
    if (s.mail_subject) setSubject(s.mail_subject)
    if (s.mail_body) setBody(s.mail_body)
  }

  const handleSaveSegment = async () => {
    try {
      const created = await saveSegment.mutateAsync({
        payload: {
          name: saveName.trim(),
          description: saveDesc.trim() || undefined,
          criteria,
          mail_subject: subject.trim() || undefined,
          mail_body: body.trim() || undefined,
        },
      })
      setSelectedSegmentId(created.segment_id)
      setSaveOpen(false)
      setSaveName('')
      setSaveDesc('')
      showToast('세그먼트가 저장되었습니다.', 'success')
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response
        ?.data?.detail
      showToast(detail ?? '세그먼트 저장에 실패했습니다.', 'danger')
    }
  }

  const handleDeleteSegment = async () => {
    if (!deleteTarget) return
    try {
      await deleteSegment.mutateAsync(deleteTarget.segment_id)
      if (selectedSegmentId === deleteTarget.segment_id) setSelectedSegmentId(null)
      setDeleteTarget(null)
      showToast('세그먼트가 삭제되었습니다. (발송 이력은 보존)', 'success')
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response
        ?.data?.detail
      showToast(detail ?? '세그먼트 삭제에 실패했습니다.', 'danger')
    }
  }

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="세그먼트 발송"
        subtitle="조건으로 고객사를 묶어 자료를 일괄 메일 발송 — 축 간 AND, 축 내 OR"
      />

      {/* ── 상단: 저장된 세그먼트 칩 — 클릭 시 조건 로드 ─────────────── */}
      <div className="flex flex-wrap items-center gap-2 rounded-3xl border border-hairline bg-graphite px-3.5 py-2.5">
        <BookmarkSimple size={16} className="shrink-0 text-ash" />
        {segments.length === 0 && (
          <span className="text-xs text-slatey">
            저장된 세그먼트가 없습니다 — 조건을 만들고 [현재 조합 저장]으로 재사용하세요.
          </span>
        )}
        {segments.map((s) => (
          <span
            key={s.segment_id}
            className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium ${
              selectedSegmentId === s.segment_id
                ? 'border-white/25 bg-elevate-strong text-bone'
                : 'border-hairline text-ash hover:bg-elevate'
            }`}
          >
            <button
              type="button"
              onClick={() => loadSegment(s)}
              title={s.description ?? '클릭하여 조건 불러오기'}
              className="hover:text-bone"
            >
              {s.name}
            </button>
            <button
              type="button"
              onClick={() => setDeleteTarget(s)}
              className="rounded-full text-smoke hover:text-rose-400"
              aria-label={`${s.name} 세그먼트 삭제`}
            >
              <X size={12} />
            </button>
          </span>
        ))}
        <button
          type="button"
          onClick={() => setSaveOpen(true)}
          disabled={!hasCriteria}
          title={hasCriteria ? '현재 조건 조합을 세그먼트로 저장' : '먼저 조건을 추가하세요'}
          className="ml-auto flex shrink-0 items-center gap-1 rounded-full border border-hairline px-3 py-1.5 text-xs font-medium text-bone hover:bg-elevate disabled:opacity-40"
        >
          <FloppyDisk size={13} />
          현재 조합 저장
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* ── 좌: 조건 빌더 ─────────────────────────────────────────── */}
        <section className="rounded-3xl border border-hairline bg-graphite p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-1.5 text-sm font-semibold text-bone">
              <Funnel size={16} className="text-ash" />
              조건 빌더
            </h2>
            <button
              type="button"
              onClick={resetCriteria}
              disabled={!hasCriteria}
              className="flex items-center gap-1 rounded-full border border-hairline px-3 py-1.5 text-xs font-medium text-bone hover:bg-elevate disabled:opacity-40"
            >
              <ArrowCounterClockwise size={13} />
              초기화
            </button>
          </div>

          <div className="space-y-3">
            {axes.map((axis) => (
              <AxisPicker
                key={axis.key}
                label={AXIS_LABELS[axis.key]}
                options={axis.options}
                selected={criteria[axis.key] ?? []}
                labelOf={axis.labelOf}
                onAdd={(v) => addValue(axis.key, v)}
                onRemove={(v) => removeValue(axis.key, v)}
              />
            ))}
          </div>

          {!hasCriteria && (
            <p className="mt-3 text-xs text-slatey">
              조건이 없으면 전체 고객사가 대상입니다. 축을 추가해 범위를 좁히세요.
            </p>
          )}
        </section>

        {/* ── 우: 실시간 미리보기 ───────────────────────────────────── */}
        <section className="rounded-3xl border border-hairline bg-graphite p-4">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-bone">대상 미리보기</h2>
            {preview.isFetching && (
              <CircleNotch size={14} className="animate-spin text-slatey" />
            )}
          </div>
          <p className="mt-2">
            <span className="text-4xl font-bold tracking-tight text-bone">
              {preview.data?.total ?? 0}
            </span>
            <span className="ml-1.5 text-sm text-ash">개사</span>
            {previewItems.length > 0 && receivable < previewItems.length && (
              <span className="ml-3 text-xs font-medium text-amber-400">
                수신 가능 {receivable} / 수신자 없음 {previewItems.length - receivable}
              </span>
            )}
          </p>

          <div className="mt-3 max-h-[420px] space-y-1 overflow-y-auto">
            {preview.isError ? (
              <EmptyState
                icon={<WarningCircle size={32} />}
                title="미리보기를 불러오지 못했습니다"
                className="!py-10"
              />
            ) : previewItems.length === 0 && !preview.isLoading ? (
              <EmptyState
                icon={<Buildings size={32} />}
                title="조건에 맞는 고객사가 없습니다"
                description="조건을 완화하거나 초기화해 보세요."
                className="!py-10"
              />
            ) : (
              previewItems.map((item) => (
                <div
                  key={item.client_id}
                  className="flex items-center gap-2 rounded-xl border border-hairline bg-elevate px-3 py-2"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-bone">
                      {item.company_name}
                    </p>
                    <p className="text-xs text-slatey">
                      {[item.region, clientType.labelOf(item.client_type)]
                        .filter(Boolean)
                        .join(' · ') || '—'}
                    </p>
                  </div>
                  {/* 계약 상태 배지 — ACTIVE가 아니면 표시 (종료·보류 오발송 예방) */}
                  {item.contract_status && item.contract_status !== 'ACTIVE' && (
                    <StatusBadge domain="contract" value={item.contract_status} />
                  )}
                  {!item.can_receive && (
                    <span
                      className="inline-flex shrink-0 items-center gap-1 rounded-full border border-amber-400/25 bg-amber-500/15 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:text-amber-300"
                      title="공통 수신자 또는 주 담당자 이메일이 없어 발송이 실패합니다"
                    >
                      <WarningCircle size={11} weight="fill" />
                      수신자 없음
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      {/* ── 하단: 발송 구성 ─────────────────────────────────────────── */}
      <section className="rounded-3xl border border-hairline bg-graphite p-4">
        <h2 className="mb-3 text-sm font-semibold text-bone">발송 구성</h2>

        {/* 첨부 파일 — 문서함에서 선택 (업로드는 문서 아카이브에서) */}
        <div className="mb-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-ash">첨부 파일</span>
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              className="flex items-center gap-1.5 rounded-full border border-hairline px-3 py-1.5 text-xs font-medium text-bone hover:bg-elevate"
            >
              <FileText size={14} />
              문서함에서 선택
            </button>
            <button
              type="button"
              onClick={() => setDbxPickerOpen(true)}
              className="flex items-center gap-1.5 rounded-full border border-hairline px-3 py-1.5 text-xs font-medium text-bone hover:bg-elevate"
            >
              <FileText size={14} />
              공용 Dropbox에서 선택
            </button>
            <span className="text-xs text-slatey">
              새 파일 업로드는 문서 아카이브에서 먼저 해주세요.
            </span>
          </div>
          {attachedDocs.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {attachedDocs.map((d) => (
                <span
                  key={d.doc_id}
                  className="inline-flex items-center gap-1 rounded-full border border-hairline bg-elevate-strong px-2.5 py-1 text-xs font-medium text-bone"
                >
                  <FileText size={12} className="text-ash" />
                  {d.title}
                  <button
                    type="button"
                    onClick={() => toggleDoc(d)}
                    className="rounded-full text-smoke hover:text-bone"
                    aria-label={`${d.title} 첨부 제거`}
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
          )}
          {dropboxPaths.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {dropboxPaths.map((p) => (
                <span
                  key={p}
                  className="inline-flex items-center gap-1 rounded-full border border-hairline bg-elevate-strong px-2.5 py-1 text-xs font-medium text-bone"
                >
                  <FileText size={12} className="text-ash" />
                  {p.split('/').pop()}
                  <button
                    type="button"
                    onClick={() => setDropboxPaths((prev) => prev.filter((x) => x !== p))}
                    className="rounded-full text-smoke hover:text-bone"
                    aria-label={`${p} 첨부 제거`}
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* mail-merge — 수신자별 각 고객사 폴더에서 개별 파일 첨부 */}
          <div className="mt-3 border-t border-hairline pt-3">
            <label className="mb-1 block text-xs font-medium text-ash">
              수신자별 개별 첨부 (각 고객사 폴더의 최신 파일)
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={mergeFolderCode}
                onChange={(e) => setMergeFolderCode(e.target.value)}
                className="h-9 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
              >
                <option value="">사용 안 함</option>
                {clientFolderCodes.options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              {mergeFolderCode && (
                <input
                  value={mergeNameContains}
                  onChange={(e) => setMergeNameContains(e.target.value)}
                  placeholder="파일명 포함(선택)"
                  className="h-9 w-40 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
                />
              )}
            </div>
            {mergeFolderCode && (
              <p className="mt-1 text-xs text-slatey">
                각 고객사의 '{clientFolderCodes.labelOf(mergeFolderCode)}' 폴더에서
                {mergeNameContains.trim() ? ` '${mergeNameContains.trim()}' 포함 ` : ' '}
                최신 파일 1개를 개별 첨부합니다. 파일이 없는 고객사는 실패로 기록됩니다.
              </p>
            )}
          </div>
        </div>

        {/* 제목·본문 — 고객사별 변수 치환 */}
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-ash">메일 제목</label>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              maxLength={200}
              className="h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ash">메일 본문</label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={6}
              className="w-full rounded-lg border border-hairline bg-graphite px-3 py-2 text-sm leading-relaxed text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
            />
            <p className="mt-1 text-xs text-slatey">
              치환 변수: {'{고객사명} {연도} {월} {담당자명}'} — 고객사별로 자동
              치환됩니다. (월간 보고서용 {'{보고서유형}'}은 여기서 치환되지 않습니다)
            </p>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-end gap-3 border-t border-hairline pt-3">
          {attachedDocs.length === 0 && dropboxPaths.length === 0 && (
            <span className="text-xs text-slatey">첨부 파일을 1개 이상 선택하세요</span>
          )}
          <button
            type="button"
            onClick={() => setConfirmOpen(true)}
            disabled={!canSend}
            className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-50"
          >
            {send.isPending ? (
              <CircleNotch size={14} className="animate-spin" />
            ) : (
              <PaperPlaneRight size={14} weight="fill" />
            )}
            발송 {targetTotal}개사
          </button>
        </div>

        {/* 직전 발송 결과 — 성공/실패 요약 + 실패 상세 */}
        {lastResult && (
          <div className="mt-3 rounded-xl border border-hairline bg-elevate p-3">
            <p className="text-xs font-semibold text-bone">
              직전 발송 결과 — 대상 {lastResult.target_count} · 성공{' '}
              <span className="text-emerald-400">{lastResult.sent_count}</span> · 실패{' '}
              <span className={lastResult.failed_count > 0 ? 'text-rose-400' : ''}>
                {lastResult.failed_count}
              </span>
            </p>
            {lastResult.failed_count > 0 && (
              <ul className="mt-2 space-y-1">
                {lastResult.details
                  .filter((d) => d.result === 'FAIL')
                  .map((d) => (
                    <li key={d.client_id} className="text-xs text-ash">
                      <WarningCircle
                        size={12}
                        weight="fill"
                        className="mr-1 inline text-rose-400"
                      />
                      <b className="text-bone">{d.client_name ?? d.client_id}</b> —{' '}
                      {d.reason ?? '알 수 없는 오류'}
                    </li>
                  ))}
              </ul>
            )}
          </div>
        )}
      </section>

      {/* ── 발송 이력 — 클릭 시 고객사별 SUCCESS/FAIL 로그 상세 ───────── */}
      <SendHistorySection />

      {/* 세그먼트 저장 Modal */}
      <Modal
        open={saveOpen}
        onClose={() => setSaveOpen(false)}
        title="현재 조합 저장"
        size="sm"
        footer={
          <>
            <button
              type="button"
              onClick={() => setSaveOpen(false)}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
            >
              취소
            </button>
            <button
              type="button"
              onClick={handleSaveSegment}
              disabled={!saveName.trim() || saveSegment.isPending}
              className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-60"
            >
              {saveSegment.isPending && <CircleNotch size={14} className="animate-spin" />}
              저장
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-ash">세그먼트 이름</label>
            <input
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              maxLength={100}
              placeholder="예: 서울 운수사 · 계약중"
              className="h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ash">설명 (선택)</label>
            <input
              value={saveDesc}
              onChange={(e) => setSaveDesc(e.target.value)}
              maxLength={200}
              className="h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
            />
          </div>
          <p className="text-xs text-slatey">
            현재 조건 조합과 메일 제목·본문이 함께 저장됩니다. (대상 {targetTotal}개사)
          </p>
        </div>
      </Modal>

      {/* 세그먼트 삭제 확인 */}
      <ConfirmDialog
        open={!!deleteTarget}
        title="세그먼트 삭제"
        message={
          <>
            <b>{deleteTarget?.name}</b> 세그먼트를 삭제합니다. 발송 이력은 보존되며,
            목록에서만 제거됩니다.
          </>
        }
        confirmLabel="삭제"
        danger
        loading={deleteSegment.isPending}
        onConfirm={handleDeleteSegment}
        onCancel={() => setDeleteTarget(null)}
      />

      {/* 문서함 픽커 Modal */}
      <DocPickerModal
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        selected={attachedDocs}
        onToggle={toggleDoc}
      />

      {/* 공용 발송자료 Dropbox 픽커 (라이브 브라우즈 공통 첨부) */}
      <DropboxPicker
        open={dbxPickerOpen}
        endpoint="/segments/dropbox/tree"
        initialSelected={dropboxPaths}
        onClose={() => setDbxPickerOpen(false)}
        onConfirm={(paths) => {
          setDropboxPaths(paths)
          setDbxPickerOpen(false)
        }}
      />

      {/* 발송 확인 다이얼로그 — 대상 수·파일 목록·제목 최종 확인 */}
      <ConfirmDialog
        open={confirmOpen}
        title={`세그먼트 발송 — ${targetTotal}개사`}
        message={
          <>
            대상 <b className="text-bone">{targetTotal}개사</b>에 아래 파일을 첨부해
            메일을 발송합니다.
            {previewItems.length - receivable > 0 && (
              <>
                <br />
                <span className="text-amber-400">
                  수신자 없음 {previewItems.length - receivable}개사는 실패로
                  기록됩니다.
                </span>
              </>
            )}
            {endedCount > 0 && (
              <>
                <br />
                <span className="text-rose-400">
                  종료 계약 고객사 {endedCount}곳이 포함되어 있습니다 — 발송 대상이
                  맞는지 확인하세요.
                </span>
              </>
            )}
            <ul className="mt-2 list-inside list-disc">
              {attachedDocs.map((d) => (
                <li key={d.doc_id} className="text-bone">
                  {d.title}
                </li>
              ))}
              {dropboxPaths.map((p) => (
                <li key={p} className="text-bone">
                  {p.split('/').pop()} <span className="text-slatey">(Dropbox)</span>
                </li>
              ))}
              {mergeFolderCode && (
                <li className="text-bone">
                  각 고객사 '{clientFolderCodes.labelOf(mergeFolderCode)}' 폴더 최신 1개{' '}
                  <span className="text-slatey">(개별 첨부)</span>
                </li>
              )}
            </ul>
            <p className="mt-2">
              제목: <b className="text-bone">{subject.trim() || '(기본 템플릿)'}</b>
            </p>
          </>
        }
        confirmLabel="발송"
        danger
        loading={send.isPending}
        onConfirm={handleSend}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  )
}

// ── 문서함 픽커 — GET /documents 검색·최근순, 복수 선택 토글 ─────────────
function DocPickerModal({
  open,
  onClose,
  selected,
  onToggle,
}: {
  open: boolean
  onClose: () => void
  selected: Document[]
  onToggle: (doc: Document) => void
}) {
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounced(search)

  const { data: documents = [], isLoading } = useQuery({
    queryKey: ['documents', 'picker', debouncedSearch],
    queryFn: async () => {
      const params: Record<string, string | number> = { page_size: 50 }
      if (debouncedSearch.trim()) params.search = debouncedSearch.trim()
      const { data } = await api.get<Document[] | Paginated<Document>>('/documents', {
        params,
      })
      return unwrapList(data).items
    },
    enabled: open,
  })

  const isSelected = (doc: Document) => selected.some((d) => d.doc_id === doc.doc_id)

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="첨부할 문서 선택"
      size="lg"
      footer={
        <button
          type="button"
          onClick={onClose}
          className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-on-primary hover:opacity-90"
        >
          선택 완료 ({selected.length})
        </button>
      }
    >
      <div className="space-y-3">
        <FilterSearch value={search} onChange={setSearch} placeholder="문서명 검색" />
        <div className="max-h-[45vh] space-y-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex justify-center py-8">
              <CircleNotch size={20} className="animate-spin text-slatey" />
            </div>
          ) : documents.length === 0 ? (
            <p className="py-8 text-center text-sm text-slatey">
              문서가 없습니다 — 문서 아카이브에서 먼저 업로드하세요.
            </p>
          ) : (
            documents.map((d) => (
              <button
                key={d.doc_id}
                type="button"
                onClick={() => onToggle(d)}
                className={`flex w-full items-center gap-2.5 rounded-xl border px-3 py-2 text-left ${
                  isSelected(d)
                    ? 'border-white/25 bg-elevate-strong'
                    : 'border-hairline hover:bg-elevate'
                }`}
              >
                {isSelected(d) ? (
                  <CheckSquare size={18} weight="fill" className="shrink-0 text-bone" />
                ) : (
                  <Square size={18} className="shrink-0 text-slatey" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-bone">{d.title}</p>
                  <p className="text-xs text-slatey">
                    {docTypeLabel(d.doc_type)} · v{d.version} ·{' '}
                    {d.client_name ?? (d.client_id ? '고객사' : '공용')} ·{' '}
                    {fmtServerDateTime(d.created_at)}
                  </p>
                </div>
              </button>
            ))
          )}
        </div>
      </div>
    </Modal>
  )
}

// ── 발송 이력 — GET /segments/sends 목록 + 행 클릭 시 로그 상세 ─────────
function SendHistorySection() {
  const { data: sends = [], isLoading } = useSegmentSends()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const detail = useSegmentSendDetail(expandedId)

  return (
    <section className="rounded-3xl border border-hairline bg-graphite p-4">
      <h2 className="mb-3 text-sm font-semibold text-bone">발송 이력</h2>
      {isLoading ? (
        <div className="flex justify-center py-6">
          <CircleNotch size={18} className="animate-spin text-slatey" />
        </div>
      ) : sends.length === 0 ? (
        <p className="py-4 text-center text-sm text-slatey">아직 발송 이력이 없습니다.</p>
      ) : (
        <div className="space-y-1">
          {sends.map((s) => {
            const expanded = expandedId === s.send_id
            return (
              <div key={s.send_id} className="rounded-xl border border-hairline">
                <button
                  type="button"
                  onClick={() => setExpandedId(expanded ? null : s.send_id)}
                  className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left hover:bg-elevate"
                >
                  {expanded ? (
                    <CaretDown size={14} className="shrink-0 text-slatey" />
                  ) : (
                    <CaretRight size={14} className="shrink-0 text-slatey" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-bone">
                      {s.subject ?? '(제목 없음)'}
                    </p>
                    <p className="text-xs text-slatey">
                      {fmtServerDateTime(s.created_at)}
                      {s.sent_by_name && ` · ${s.sent_by_name}`}
                    </p>
                  </div>
                  <p className="shrink-0 text-xs text-ash">
                    대상 {s.target_count} · 성공{' '}
                    <b className="text-emerald-400">{s.sent_count}</b> · 실패{' '}
                    <b className={s.failed_count > 0 ? 'text-rose-400' : 'text-ash'}>
                      {s.failed_count}
                    </b>
                  </p>
                </button>
                {expanded && (
                  <div className="border-t border-hairline px-3 py-2">
                    {detail.isLoading ? (
                      <div className="flex justify-center py-3">
                        <CircleNotch size={16} className="animate-spin text-slatey" />
                      </div>
                    ) : (detail.data?.logs?.length ?? 0) === 0 ? (
                      <p className="py-2 text-xs text-slatey">
                        고객사별 로그가 없습니다.
                      </p>
                    ) : (
                      <ul className="space-y-1">
                        {detail.data!.logs.map((log) => (
                          <li
                            key={log.log_id}
                            className="flex items-baseline gap-2 text-xs"
                          >
                            <span
                              className={`shrink-0 font-semibold ${
                                log.result === 'SUCCESS'
                                  ? 'text-emerald-400'
                                  : 'text-rose-400'
                              }`}
                            >
                              {log.result === 'SUCCESS' ? '성공' : '실패'}
                            </span>
                            <span className="shrink-0 font-medium text-bone">
                              {log.client_name ?? log.client_id}
                            </span>
                            {log.reason && (
                              <span className="min-w-0 truncate text-ash" title={log.reason}>
                                — {log.reason}
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

// ── 축 멀티선택 — 드롭다운으로 추가, 선택값은 제거 가능한 칩 ─────────────
function AxisPicker({
  label,
  options,
  selected,
  labelOf,
  onAdd,
  onRemove,
}: {
  label: string
  options: { value: string; label: string }[]
  selected: string[]
  labelOf: (value: string) => string
  onAdd: (value: string) => void
  onRemove: (value: string) => void
}) {
  const remaining = options.filter((o) => !selected.includes(o.value))
  return (
    <div>
      <div className="flex items-center gap-2">
        <span className="w-20 shrink-0 text-xs font-medium text-ash">{label}</span>
        <select
          value=""
          onChange={(e) => e.target.value && onAdd(e.target.value)}
          disabled={remaining.length === 0}
          className="h-9 min-w-0 flex-1 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none disabled:opacity-40"
          aria-label={`${label} 조건 추가`}
        >
          <option value="">
            {remaining.length === 0 && options.length > 0 ? '모두 선택됨' : '+ 조건 추가'}
          </option>
          {remaining.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      {selected.length > 0 && (
        <div className="mt-1.5 ml-22 flex flex-wrap gap-1.5">
          {selected.map((value) => (
            <span
              key={value}
              className="inline-flex items-center gap-1 rounded-full border border-hairline bg-elevate-strong px-2.5 py-1 text-xs font-medium text-bone"
            >
              {labelOf(value)}
              <button
                type="button"
                onClick={() => onRemove(value)}
                className="rounded-full text-smoke hover:text-bone"
                aria-label={`${labelOf(value)} 조건 제거`}
              >
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
