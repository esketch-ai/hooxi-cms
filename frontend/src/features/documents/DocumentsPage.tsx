// SCR-13 문서 아카이브 — 고객사 폴더 트리(좌) + 문서 리스트(우)
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CircleNotch,
  DownloadSimple,
  FolderOpen,
  FolderSimple,
  Plus,
  TreeStructure,
  Trash,
} from '@phosphor-icons/react'
import { useAuth } from '../../app/AuthProvider'
import { PageHeader } from '../../components/PageHeader'
import { FilterBar, FilterSelect } from '../../components/FilterBar'
import { DataTable, type Column } from '../../components/DataTable'
import { EmptyState } from '../../components/EmptyState'
import { Modal } from '../../components/Modal'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { FileUploader } from '../../components/FileUploader'
import { DocumentPreviewModal } from '../../components/DocumentPreviewModal'
import { useToast } from '../../components/Toast'
import { api } from '../../lib/api/client'
import {
  isDeletableDoc,
  unwrapList,
  useApplyReconcile,
  useClientOptions,
  useCodes,
  useDeleteDocument,
  useDropboxTree,
  usePreviewReconcile,
  type ReconcileApply,
  type ReconcilePreview,
} from '../../lib/api/queries'
import { downloadDocument, downloadErrorMessage, previewKind } from '../../lib/download'
import { fmtServerDateTime } from '../../lib/format'
import type { DocType, Document, Paginated } from '../../types'

export const DOC_TYPE_OPTIONS: { value: DocType; label: string }[] = [
  { value: 'CONTRACT', label: '계약서' },
  { value: 'REPORT', label: '보고서' },
  { value: 'FORM', label: '표준 양식' },
  { value: 'PHOTO', label: '현장 사진' },
  { value: 'SIGN', label: '서명' },
  { value: 'ETC', label: '기타' },
]

export const docTypeLabel = (t: string) =>
  DOC_TYPE_OPTIONS.find((o) => o.value === t)?.label ?? t

export function DocumentsPage() {
  const { data: clients = [] } = useClientOptions()
  const { showToast } = useToast()
  const { user } = useAuth()
  const isAdmin = user?.role === 'ADMIN'
  // 폴더명 규칙 점검/교정 모달(ADMIN 전용)
  const [reconcileOpen, setReconcileOpen] = useState(false)

  // 다운로드 실패(404/503 등) 시 에러 토스트 (L-3)
  const handleDownload = async (docId: string, title?: string) => {
    try {
      await downloadDocument(docId, title)
    } catch (err) {
      showToast(downloadErrorMessage(err), 'danger')
    }
  }

  // 폴더 트리 선택: null=전체, 'COMMON'=공용(미지정), client_id
  const [folder, setFolder] = useState<string | null>(null)
  // 보기 모드: 'records'=앱 문서 대장(tb_document) / 'dropbox'=Dropbox 폴더 라이브 브라우즈
  // (dropbox 보기는 특정 고객사 폴더 선택 시에만 의미 — Dropbox에 직접 넣은 파일까지 열람)
  const [view, setView] = useState<'records' | 'dropbox'>('records')
  const isClientFolder = !!folder && folder !== 'COMMON'
  // Dropbox 폴더 라이브 보기가 가능한 노드(고객사 폴더 + 공용 발송자료 폴더)
  const canBrowseDropbox = isClientFolder || folder === 'COMMON'
  // 선택 노드별 Dropbox 트리/파일 엔드포인트(고객사=고객사 폴더, 공용=공용_발송자료)
  const dropboxEndpoints =
    folder === 'COMMON'
      ? { tree: '/segments/dropbox/tree', file: '/segments/dropbox/file' }
      : isClientFolder
        ? { tree: `/clients/${folder}/dropbox/tree`, file: `/clients/${folder}/dropbox/file` }
        : null
  const [docType, setDocType] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)
  // 문서명 클릭 → 미리보기(이미지/PDF만) — 다운로드 아이콘은 별도 유지
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null)
  const [deleteDoc, setDeleteDoc] = useState<Document | null>(null)
  const deleteDocument = useDeleteDocument()

  const params = useMemo(() => {
    const p: Record<string, string | number> = { page_size: 200 }
    if (folder && folder !== 'COMMON') p.client_id = folder
    if (docType) p.doc_type = docType
    if (dateFrom) p.date_from = dateFrom
    if (dateTo) p.date_to = dateTo
    return p
  }, [folder, docType, dateFrom, dateTo])

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['documents', params],
    queryFn: async () => {
      const { data } = await api.get<Document[] | Paginated<Document>>('/documents', { params })
      return unwrapList(data).items
    },
  })

  const documents = useMemo(() => {
    const items = data ?? []
    // 공용(고객사 미지정) 폴더는 클라이언트 필터링
    if (folder === 'COMMON') return items.filter((d) => !d.client_id)
    return items
  }, [data, folder])

  const columns: Column<Document>[] = [
    {
      key: 'title',
      header: '문서명',
      render: (d) => (
        <div className="min-w-0">
          {previewKind(d) ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                setPreviewDoc(d)
              }}
              className="block max-w-full truncate text-left font-medium text-bone hover:underline"
              title="미리보기"
            >
              {d.title}
            </button>
          ) : (
            <p className="truncate font-medium text-bone">{d.title}</p>
          )}
          {!folder && (
            <p className="text-xs text-slatey">
              {d.client_name ?? (d.client_id ? '고객사' : '공용')}
            </p>
          )}
        </div>
      ),
    },
    {
      key: 'type',
      header: '유형',
      render: (d) => (
        <span className="inline-flex rounded-full border border-hairline bg-elevate-strong px-2 py-0.5 text-xs font-medium text-ash">
          {docTypeLabel(d.doc_type)}
        </span>
      ),
    },
    {
      key: 'version',
      header: '버전',
      render: (d) => <span className="font-mono text-xs text-ash">v{d.version}</span>,
    },
    {
      key: 'uploader',
      header: '업로더',
      render: (d) => <span className="text-ash">{d.uploaded_by_name ?? '—'}</span>,
    },
    {
      key: 'date',
      header: '업로드일',
      render: (d) => <span className="text-xs text-ash">{fmtServerDateTime(d.created_at)}</span>,
    },
    {
      key: 'actions',
      header: '',
      className: 'text-right',
      render: (d) => (
        <div className="inline-flex items-center gap-1">
          <button
            type="button"
            className="rounded-lg p-1.5 text-smoke hover:bg-elevate hover:text-bone"
            title="다운로드"
            onClick={(e) => {
              e.stopPropagation()
              void handleDownload(d.doc_id, d.title)
            }}
          >
            <DownloadSimple size={16} />
          </button>
          {/* 리포트·서명은 보존 대상이라 삭제 버튼 비노출 (isDeletableDoc) */}
          {isDeletableDoc(d.doc_type) && (
            <button
              type="button"
              className="rounded-lg p-1.5 text-smoke hover:bg-rose-500/10 hover:text-rose-400"
              title="삭제"
              aria-label={`${d.title} 삭제`}
              onClick={(e) => {
                e.stopPropagation()
                setDeleteDoc(d)
              }}
            >
              <Trash size={16} />
            </button>
          )}
        </div>
      ),
    },
  ]

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="문서 아카이브"
        subtitle="계약서·표준 양식·현장 사진·발송 보고서 문서함"
        actions={
          <div className="flex items-center gap-2">
            {isAdmin && (
              <button
                type="button"
                onClick={() => setReconcileOpen(true)}
                className="flex items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate"
                title="고객사 Dropbox 폴더명이 규칙(지역+명+분류)과 일치하는지 점검·교정"
              >
                <TreeStructure size={16} />
                폴더명 규칙 점검
              </button>
            )}
            <button
              type="button"
              onClick={() => setUploadOpen(true)}
              className="flex items-center gap-1.5 rounded-full bg-primary px-3.5 py-2 text-sm font-medium text-on-primary hover:opacity-90"
            >
              <Plus size={16} weight="bold" />
              문서 업로드
            </button>
          </div>
        }
      />

      <FilterBar>
        <FilterSelect
          label="유형"
          value={docType}
          onChange={setDocType}
          options={DOC_TYPE_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
        />
        <label className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-ash">기간</span>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="h-9 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
            aria-label="시작일"
          />
          <span className="text-slatey">~</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="h-9 rounded-lg border border-hairline bg-graphite px-2 text-sm text-bone focus:border-white/30 focus:outline-none"
            aria-label="종료일"
          />
        </label>
      </FilterBar>

      <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
        {/* 고객사 폴더 트리 */}
        <aside className="h-fit rounded-3xl border border-hairline bg-graphite p-2">
          <FolderButton
            active={folder === null}
            label="전체 문서"
            onClick={() => setFolder(null)}
          />
          <FolderButton
            active={folder === 'COMMON'}
            label="공용 (양식 등)"
            onClick={() => setFolder('COMMON')}
          />
          <p className="mt-2 mb-1 px-2 text-[11px] font-semibold tracking-wider text-slatey uppercase">
            고객사
          </p>
          <div className="max-h-[50vh] overflow-y-auto">
            {clients.map((c) => (
              <FolderButton
                key={c.client_id}
                active={folder === c.client_id}
                label={c.company_name}
                onClick={() => setFolder(c.client_id)}
              />
            ))}
            {clients.length === 0 && (
              <p className="px-2 py-2 text-xs text-slatey">고객사가 없습니다</p>
            )}
          </div>
        </aside>

        {/* 문서 리스트 / Dropbox 폴더 보기 */}
        <div className="space-y-3">
          {canBrowseDropbox && (
            <div className="flex w-fit gap-1 rounded-full border border-hairline bg-graphite p-1 text-sm">
              <button
                type="button"
                onClick={() => setView('records')}
                className={`rounded-full px-3 py-1 font-medium ${view === 'records' ? 'bg-primary text-on-primary' : 'text-ash hover:text-bone'}`}
              >
                문서 대장
              </button>
              <button
                type="button"
                onClick={() => setView('dropbox')}
                className={`rounded-full px-3 py-1 font-medium ${view === 'dropbox' ? 'bg-primary text-on-primary' : 'text-ash hover:text-bone'}`}
                title="Dropbox 폴더를 직접 열람(앱 미등록 파일 포함)"
              >
                Dropbox 폴더
              </button>
            </div>
          )}
          {canBrowseDropbox && view === 'dropbox' && dropboxEndpoints ? (
            <DropboxFolderBrowser
              key={folder}
              treeEndpoint={dropboxEndpoints.tree}
              fileEndpoint={dropboxEndpoints.file}
            />
          ) : isError ? (
            <EmptyState
              icon={<FolderOpen size={36} />}
              title="문서를 불러오지 못했습니다"
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
              rows={documents}
              rowKey={(d) => d.doc_id}
              isLoading={isLoading}
              emptyTitle="문서가 없습니다"
              emptyDescription="[문서 업로드]로 계약서·양식·현장 사진을 보관하세요."
              renderCard={(d) => (
                <div className="flex items-center gap-3">
                  <div className="min-w-0 flex-1">
                    {previewKind(d) ? (
                      <button
                        type="button"
                        onClick={() => setPreviewDoc(d)}
                        className="block max-w-full truncate text-left text-sm font-medium text-bone hover:underline"
                        title="미리보기"
                      >
                        {d.title}
                      </button>
                    ) : (
                      <p className="truncate text-sm font-medium text-bone">{d.title}</p>
                    )}
                    <p className="text-xs text-slatey">
                      {docTypeLabel(d.doc_type)} · v{d.version} · {fmtServerDateTime(d.created_at)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleDownload(d.doc_id, d.title)}
                    className="rounded-lg p-2 text-smoke hover:bg-elevate"
                    aria-label="다운로드"
                  >
                    <DownloadSimple size={18} />
                  </button>
                </div>
              )}
            />
          )}
        </div>
      </div>

      <DocumentUploadModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        defaultClientId={folder && folder !== 'COMMON' ? folder : ''}
      />
      <DocumentPreviewModal doc={previewDoc} onClose={() => setPreviewDoc(null)} />
      {isAdmin && (
        <ReconcileFoldersModal open={reconcileOpen} onClose={() => setReconcileOpen(false)} />
      )}
      <ConfirmDialog
        open={!!deleteDoc}
        title="문서 삭제"
        message={
          <>
            <b>{deleteDoc?.title}</b> 문서를 삭제합니다. 저장된 파일도 함께 제거되며, 되돌릴 수
            없습니다.
          </>
        }
        confirmLabel="삭제"
        danger
        loading={deleteDocument.isPending}
        onCancel={() => setDeleteDoc(null)}
        onConfirm={async () => {
          if (!deleteDoc) return
          try {
            await deleteDocument.mutateAsync(deleteDoc.doc_id)
            showToast('문서가 삭제되었습니다.', 'success')
            setDeleteDoc(null)
          } catch (err) {
            const detail = (err as { response?: { data?: { detail?: string } } })?.response
              ?.data?.detail
            showToast(detail || '삭제에 실패했습니다.', 'danger')
          }
        }}
      />
    </div>
  )
}

// ── 폴더명 규칙 점검/교정 Modal(ADMIN 전용) ──────────────────────────
// 미리보기(dry-run)로 이동/충돌/유지 후보를 계산 → [적용]으로 규칙 경로로 실제 이동.
// 파일은 보존(폴더 이동만). 미설정 503/권한 403은 detail 토스트로 안내.
const reconcileActionLabel = (a: ReconcilePreview['items'][number]['action']) =>
  a === 'conflict' ? '충돌' : a === 'move' ? '이동' : '유지'
const reconcileReasonLabel = (r: ReconcilePreview['items'][number]['reason']) =>
  r === 'root_changed' ? '루트 변경' : r === 'name_changed' ? '개명' : '—'

function ReconcileFoldersModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { showToast } = useToast()
  const preview = usePreviewReconcile()
  const apply = useApplyReconcile()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [result, setResult] = useState<ReconcileApply | null>(null)

  const detailOf = (err: unknown) =>
    (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail

  // 모달 열릴 때 미리보기 자동 실행 / 상태 리셋
  useEffect(() => {
    if (!open) return
    setResult(null)
    apply.reset()
    preview.mutate(undefined, {
      onError: (err) =>
        showToast(detailOf(err) ?? '미리보기를 불러오지 못했습니다.', 'danger'),
    })
    // 열릴 때 1회만 실행 (mutation 객체는 매 렌더 갱신되므로 open만 의존)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const data = preview.data
  const rows = useMemo(
    () => (data?.items ?? []).filter((i) => i.action !== 'skip_match'),
    [data],
  )
  const canApply = !!data && data.move_count > 0

  const handleApply = async () => {
    try {
      const res = await apply.mutateAsync()
      setResult(res)
      setConfirmOpen(false)
      if (res.failed > 0 || res.conflicts > 0) {
        showToast(
          `이동 ${res.moved} · 충돌 ${res.conflicts} · 실패 ${res.failed}`,
          res.failed > 0 ? 'danger' : 'info',
        )
      } else {
        showToast(`${res.moved}건을 규칙 경로로 이동했습니다.`, 'success')
      }
    } catch (err) {
      setConfirmOpen(false)
      showToast(detailOf(err) ?? '적용에 실패했습니다.', 'danger')
    }
  }

  return (
    <>
      <Modal open={open} onClose={onClose} title="폴더명 규칙 점검" size="xl">
        {preview.isPending ? (
          <div className="flex items-center gap-2 px-2 py-10 text-sm text-slatey">
            <CircleNotch size={16} className="animate-spin" /> 규칙 대조 중…
          </div>
        ) : preview.isError ? (
          <EmptyState
            icon={<FolderOpen size={36} />}
            title="미리보기를 불러올 수 없습니다"
            description={detailOf(preview.error) ?? 'Dropbox 연동/권한 상태를 확인하세요.'}
          />
        ) : data ? (
          <div className="space-y-3">
            {/* 요약 */}
            <div className="flex flex-wrap gap-2 text-sm">
              <span className="rounded-full border border-hairline bg-elevate-strong px-3 py-1 text-ash">
                총 {data.total}
              </span>
              <span className="rounded-full border border-hairline bg-elevate-strong px-3 py-1 text-bone">
                이동 {data.move_count}
              </span>
              <span className="rounded-full border border-hairline bg-elevate-strong px-3 py-1 text-amber-400">
                충돌 {data.conflict_count}
              </span>
              <span className="rounded-full border border-hairline bg-elevate-strong px-3 py-1 text-slatey">
                유지 {data.skip_count}
              </span>
            </div>

            {/* 적용 결과(있으면) */}
            {result && (
              <div
                className={`rounded-2xl border px-3 py-2 text-sm ${
                  result.failed > 0
                    ? 'border-rose-500/40 bg-rose-500/10 text-rose-300'
                    : result.conflicts > 0
                      ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                      : 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                }`}
              >
                적용 결과 — 이동 {result.moved} · 충돌 {result.conflicts} · 실패 {result.failed}
                {' / '}대상 {result.total_candidates}건
              </div>
            )}

            {rows.length === 0 ? (
              <p className="rounded-2xl border border-hairline bg-graphite px-3 py-6 text-center text-sm text-slatey">
                {data.skip_count > 0
                  ? `이동할 폴더가 없습니다 — ${data.skip_count}건 이미 규칙과 일치합니다.`
                  : '이동할 폴더가 없습니다.'}
              </p>
            ) : (
              <div className="max-h-[45vh] overflow-y-auto rounded-2xl border border-hairline">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 bg-elevate-strong text-xs text-slatey">
                    <tr>
                      <th className="px-3 py-2 font-medium">회사명</th>
                      <th className="px-3 py-2 font-medium">현재 경로</th>
                      <th className="px-3 py-2 font-medium">제안 경로</th>
                      <th className="px-3 py-2 font-medium">판정</th>
                      <th className="px-3 py-2 font-medium">이유</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {rows.map((it) => (
                      <tr key={it.client_id}>
                        <td className="px-3 py-2 text-bone">{it.company_name}</td>
                        <td className="px-3 py-2 font-mono text-xs text-slatey">
                          {it.current_path}
                        </td>
                        <td className="px-3 py-2 font-mono text-xs text-ash">
                          {it.proposed_path}
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                              it.action === 'conflict'
                                ? 'bg-amber-500/15 text-amber-400'
                                : 'bg-primary/15 text-primary'
                            }`}
                          >
                            {reconcileActionLabel(it.action)}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-xs text-ash">
                          {reconcileReasonLabel(it.reason)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex justify-end gap-2 border-t border-hairline pt-3">
              <button
                type="button"
                onClick={onClose}
                className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
              >
                닫기
              </button>
              <button
                type="button"
                onClick={() => setConfirmOpen(true)}
                disabled={!canApply || apply.isPending}
                className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
              >
                {apply.isPending && <CircleNotch size={14} className="animate-spin" />}
                적용
              </button>
            </div>
          </div>
        ) : null}
      </Modal>

      <ConfirmDialog
        open={confirmOpen}
        title="폴더명 규칙 적용"
        message={
          <>
            이동 <b>{data?.move_count ?? 0}</b>건을 규칙 경로로 옮깁니다. 파일은 보존되며 삭제되지
            않습니다. 진행할까요?
          </>
        }
        confirmLabel="적용"
        loading={apply.isPending}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={handleApply}
      />
    </>
  )
}

// Dropbox 폴더 라이브 브라우저 — 앱 미등록 파일 포함, 파일 클릭 시 임시링크로 열람.
// treeEndpoint/fileEndpoint 주입형(고객사·공용 등 재사용). 읽기 전용.
function DropboxFolderBrowser({
  treeEndpoint,
  fileEndpoint,
}: {
  treeEndpoint: string
  fileEndpoint: string
}) {
  const { showToast } = useToast()
  const [path, setPath] = useState<string | null>(null) // null = 폴더 루트
  const [rootPath, setRootPath] = useState<string | null>(null)
  const { data, isLoading, isError, error } = useDropboxTree(treeEndpoint, path)

  // 엔드포인트 변경 시엔 부모가 key로 remount하므로 별도 리셋 불필요(초기 상태로 새로 마운트).
  useEffect(() => {
    if (data && rootPath === null) setRootPath(data.path)
  }, [data, rootPath])

  const currentPath = data?.path ?? ''
  const atRoot = !rootPath || currentPath === rootPath
  const goUp = () => {
    const parent = currentPath.replace(/\/[^/]*$/, '')
    setPath(rootPath && parent.length < rootPath.length ? rootPath : parent)
  }
  const openFile = async (p: string) => {
    try {
      const { data: link } = await api.get<{ url: string }>(fileEndpoint, {
        params: { path: p },
      })
      window.open(link.url, '_blank', 'noopener')
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      showToast(detail ?? '파일을 열 수 없습니다.', 'danger')
    }
  }

  if (isError) {
    const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    return (
      <EmptyState
        icon={<FolderOpen size={36} />}
        title="Dropbox 폴더를 열 수 없습니다"
        description={detail ?? 'Dropbox 연동/폴더 상태를 확인하세요.'}
      />
    )
  }

  return (
    <div className="rounded-3xl border border-hairline bg-graphite p-3">
      {/* 경로 바 */}
      <div className="mb-2 flex items-center gap-2 text-xs text-slatey">
        <button
          type="button"
          onClick={goUp}
          disabled={atRoot}
          className="rounded-lg border border-hairline px-2 py-1 text-bone hover:bg-elevate disabled:opacity-40"
        >
          ↑ 상위로
        </button>
        <span className="truncate font-mono">{currentPath || '/'}</span>
      </div>
      {isLoading ? (
        <div className="flex items-center gap-2 px-2 py-6 text-sm text-slatey">
          <CircleNotch size={16} className="animate-spin" /> 불러오는 중…
        </div>
      ) : !data || data.entries.length === 0 ? (
        <p className="px-2 py-6 text-center text-sm text-slatey">이 폴더는 비어 있습니다.</p>
      ) : (
        <ul className="divide-y divide-hairline">
          {data.entries.map((e) =>
            e.is_dir ? (
              <li key={e.path_display}>
                <button
                  type="button"
                  onClick={() => setPath(e.path_display)}
                  className="flex w-full items-center gap-2 px-2 py-2 text-left text-sm text-bone hover:bg-elevate"
                >
                  <FolderSimple size={16} className="text-amber-500" />
                  <span className="truncate">{e.name}</span>
                </button>
              </li>
            ) : (
              <li key={e.path_display}>
                <button
                  type="button"
                  onClick={() => void openFile(e.path_display)}
                  className="flex w-full items-center gap-2 px-2 py-2 text-left text-sm text-ash hover:bg-elevate hover:text-bone"
                  title="새 탭에서 열기"
                >
                  <DownloadSimple size={15} className="shrink-0 text-smoke" />
                  <span className="truncate">{e.name}</span>
                  {e.size != null && (
                    <span className="ml-auto shrink-0 text-xs text-slatey">
                      {Math.max(1, Math.round(e.size / 1024))} KB
                    </span>
                  )}
                </button>
              </li>
            ),
          )}
        </ul>
      )}
    </div>
  )
}

function FolderButton({
  active,
  label,
  onClick,
}: {
  active: boolean
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm ${
        active
          ? 'bg-elevate-strong font-semibold text-bone'
          : 'text-ash hover:bg-elevate'
      }`}
    >
      {active ? (
        <FolderOpen size={16} weight="fill" className="shrink-0 text-ash" />
      ) : (
        <FolderSimple size={16} className="shrink-0 text-slatey" />
      )}
      <span className="truncate">{label}</span>
    </button>
  )
}

// ── 업로드 Modal ─────────────────────────────────────────────────────
function DocumentUploadModal({
  open,
  onClose,
  defaultClientId,
}: {
  open: boolean
  onClose: () => void
  defaultClientId: string
}) {
  const { showToast } = useToast()
  const { data: clients = [] } = useClientOptions()
  // 저장 폴더(6구분) — tb_code CLIENT_FOLDER active 코드. 정산·수집데이터 등 직접 선택.
  const { options: folderOptions } = useCodes('CLIENT_FOLDER')
  const queryClient = useQueryClient()

  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [clientId, setClientId] = useState(defaultClientId)
  const [docType, setDocType] = useState<DocType>('ETC')
  const [folderCode, setFolderCode] = useState('')

  // 저장 폴더 기본값 = 문서 유형에 대응하는 폴더(오분류 방지). 사용자가 정산 등으로 직접 변경 가능.
  useEffect(() => {
    if (folderOptions.length === 0) return
    const map: Record<string, string> = {
      CONTRACT: 'CONTRACT', REPORT: 'REPORT', PHOTO: 'ASSET_AUTH',
      SIGN: 'EVIDENCE', FORM: 'EVIDENCE', ETC: 'EVIDENCE',
    }
    const mapped = map[docType] ?? 'EVIDENCE'
    setFolderCode(folderOptions.some((o) => o.value === mapped) ? mapped : folderOptions[0].value)
  }, [docType, folderOptions])

  const upload = useMutation({
    mutationFn: async () => {
      const form = new FormData()
      if (file) form.append('file', file)
      form.append('title', title.trim() || (file?.name ?? ''))
      form.append('doc_type', docType)
      if (folderCode) form.append('folder_code', folderCode)
      if (clientId) form.append('client_id', clientId)
      const { data } = await api.post('/documents', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60_000,
      })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['clients'] })
    },
  })

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!file) {
      showToast('업로드할 파일을 선택해 주세요.', 'danger')
      return
    }
    if (!folderCode) {
      showToast('저장 폴더를 선택해 주세요.', 'danger')
      return
    }
    try {
      await upload.mutateAsync()
      showToast('문서가 업로드되었습니다.', 'success')
      setFile(null)
      setTitle('')
      onClose()
    } catch {
      showToast('업로드에 실패했습니다.', 'danger')
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="문서 업로드" size="md">
      <form onSubmit={handleSubmit} className="space-y-3">
        <FileUploader file={file} onChange={setFile} enableCamera />
        <div>
          <label className="mb-1 block text-xs font-medium text-ash">문서명</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={file?.name ?? '미입력 시 파일명 사용'}
            className="h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone placeholder:text-slatey focus:border-white/30 focus:outline-none"
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-ash">고객사</label>
            <select
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              className="h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone focus:border-white/30 focus:outline-none"
            >
              <option value="">공용 (미지정)</option>
              {clients.map((c) => (
                <option key={c.client_id} value={c.client_id}>
                  {c.company_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ash">문서 유형</label>
            <select
              value={docType}
              onChange={(e) => setDocType(e.target.value as DocType)}
              className="h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone focus:border-white/30 focus:outline-none"
            >
              {DOC_TYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-ash">저장 폴더</label>
          <select
            value={folderCode}
            onChange={(e) => setFolderCode(e.target.value)}
            className="h-10 w-full rounded-lg border border-hairline bg-graphite px-3 text-sm text-bone focus:border-white/30 focus:outline-none"
          >
            {folderOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-slatey">
            실제 저장되는 고객사 폴더(계약서·정산·보고서·자산·인증정보·수집데이터·증빙자료)입니다.
          </p>
        </div>
        <div className="flex justify-end gap-2 border-t border-hairline pt-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={upload.isPending}
            className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-60"
          >
            {upload.isPending && <CircleNotch size={14} className="animate-spin" />}
            업로드
          </button>
        </div>
      </form>
    </Modal>
  )
}
