// SCR-13 문서 아카이브 — 고객사 폴더 트리(좌) + 문서 리스트(우)
import { useMemo, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CircleNotch,
  DownloadSimple,
  FolderOpen,
  FolderSimple,
  Plus,
} from '@phosphor-icons/react'
import { PageHeader } from '../../components/PageHeader'
import { FilterBar, FilterSelect } from '../../components/FilterBar'
import { DataTable, type Column } from '../../components/DataTable'
import { EmptyState } from '../../components/EmptyState'
import { Modal } from '../../components/Modal'
import { FileUploader } from '../../components/FileUploader'
import { useToast } from '../../components/Toast'
import { api } from '../../lib/api/client'
import { unwrapList, useClientOptions } from '../../lib/api/queries'
import { downloadDocument, downloadErrorMessage } from '../../lib/download'
import { fmtServerDateTime } from '../../lib/format'
import type { DocType, Document, Paginated } from '../../types'

const DOC_TYPE_OPTIONS: { value: DocType; label: string }[] = [
  { value: 'CONTRACT', label: '계약서' },
  { value: 'REPORT', label: '보고서' },
  { value: 'FORM', label: '표준 양식' },
  { value: 'PHOTO', label: '현장 사진' },
  { value: 'ETC', label: '기타' },
]

const docTypeLabel = (t: string) => DOC_TYPE_OPTIONS.find((o) => o.value === t)?.label ?? t

export function DocumentsPage() {
  const { data: clients = [] } = useClientOptions()
  const { showToast } = useToast()

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
  const [docType, setDocType] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)

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
          <p className="truncate font-medium text-bone">{d.title}</p>
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
        <span className="inline-flex rounded-full border border-hairline bg-white/10 px-2 py-0.5 text-xs font-medium text-ash">
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
      key: 'download',
      header: '다운로드',
      className: 'text-right',
      render: (d) => (
        <button
          type="button"
          className="inline-flex rounded-lg p-1.5 text-smoke hover:bg-white/5 hover:text-bone"
          title="다운로드"
          onClick={(e) => {
            e.stopPropagation()
            void handleDownload(d.doc_id, d.title)
          }}
        >
          <DownloadSimple size={16} />
        </button>
      ),
    },
  ]

  return (
    <div className="animate-fade-in space-y-4">
      <PageHeader
        title="문서 아카이브"
        subtitle="계약서·표준 양식·현장 사진·발송 보고서 문서함"
        actions={
          <button
            type="button"
            onClick={() => setUploadOpen(true)}
            className="hidden items-center gap-1.5 rounded-full bg-snow px-3.5 py-2 text-sm font-medium text-graphite hover:bg-white/90 sm:flex"
          >
            <Plus size={16} weight="bold" />
            문서 업로드
          </button>
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

        {/* 문서 리스트 */}
        <div>
          {isError ? (
            <EmptyState
              icon={<FolderOpen size={36} />}
              title="문서를 불러오지 못했습니다"
              action={
                <button
                  type="button"
                  onClick={() => refetch()}
                  className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-white/5"
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
                    <p className="truncate text-sm font-medium text-bone">{d.title}</p>
                    <p className="text-xs text-slatey">
                      {docTypeLabel(d.doc_type)} · v{d.version} · {fmtServerDateTime(d.created_at)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleDownload(d.doc_id, d.title)}
                    className="rounded-lg p-2 text-smoke hover:bg-white/5"
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
          ? 'bg-white/10 font-semibold text-bone'
          : 'text-ash hover:bg-white/5'
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
  const queryClient = useQueryClient()

  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [clientId, setClientId] = useState(defaultClientId)
  const [docType, setDocType] = useState<DocType>('ETC')

  const upload = useMutation({
    mutationFn: async () => {
      const form = new FormData()
      if (file) form.append('file', file)
      form.append('title', title.trim() || (file?.name ?? ''))
      form.append('doc_type', docType)
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
        <FileUploader file={file} onChange={setFile} />
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
        <div className="flex justify-end gap-2 border-t border-hairline pt-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-white/5"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={upload.isPending}
            className="flex items-center gap-1.5 rounded-full bg-snow px-4 py-2 text-sm font-medium text-graphite hover:bg-white/90 disabled:opacity-60"
          >
            {upload.isPending && <CircleNotch size={14} className="animate-spin" />}
            업로드
          </button>
        </div>
      </form>
    </Modal>
  )
}
