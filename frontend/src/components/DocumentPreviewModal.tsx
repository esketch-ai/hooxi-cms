// 문서 미리보기 모달 — 이미지/PDF를 다운로드 없이 바로 확인 (문서함·리포트 등 목록 공용)
// JWT 헤더가 필요해 <img src>/<iframe src> 직접 지정 불가 → Blob 조회 후 object URL로 렌더
import { useEffect, useState } from 'react'
import { ArrowSquareOut, CircleNotch, DownloadSimple } from '@phosphor-icons/react'
import { Modal } from './Modal'
import { useToast } from './Toast'
import {
  downloadDocument,
  downloadErrorMessage,
  fetchDocumentBlob,
  previewKind,
  previewMimeType,
} from '../lib/download'
import type { Document } from '../types'

export function DocumentPreviewModal({
  doc,
  onClose,
}: {
  /** 대상 문서 — null이면 닫힘 */
  doc: Pick<Document, 'doc_id' | 'title' | 'file_url'> | null
  onClose: () => void
}) {
  const { showToast } = useToast()
  const [objectUrl, setObjectUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const kind = doc ? previewKind(doc) : null

  // 열릴 때 Blob 조회 → 확장자 MIME으로 재래핑(리다이렉트 응답이 octet-stream일 수 있음)
  // 닫힘·언마운트·doc 변경 시 object URL 해제
  useEffect(() => {
    if (!doc) return
    let cancelled = false
    let url: string | null = null
    setObjectUrl(null)
    setError(null)
    fetchDocumentBlob(doc.doc_id)
      .then((data) => {
        const u = URL.createObjectURL(new Blob([data], { type: previewMimeType(doc) }))
        if (cancelled) {
          URL.revokeObjectURL(u)
          return
        }
        url = u
        setObjectUrl(u)
      })
      .catch((err) => {
        if (!cancelled) setError(downloadErrorMessage(err))
      })
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
      setObjectUrl(null)
      setError(null)
    }
  }, [doc])

  const handleDownload = async () => {
    if (!doc) return
    try {
      await downloadDocument(doc.doc_id, doc.title)
    } catch (err) {
      showToast(downloadErrorMessage(err), 'danger')
    }
  }

  return (
    <Modal
      open={doc != null}
      onClose={onClose}
      title={doc?.title}
      size="xl"
      footer={
        <>
          {kind === 'pdf' && objectUrl && (
            <button
              type="button"
              onClick={() => window.open(objectUrl)}
              className="flex items-center gap-1.5 rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
            >
              <ArrowSquareOut size={14} />
              새 탭에서 열기
            </button>
          )}
          <button
            type="button"
            onClick={handleDownload}
            className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90"
          >
            <DownloadSimple size={14} />
            다운로드
          </button>
        </>
      }
    >
      {/* 로딩 / 에러 / 렌더 3상태 */}
      {!objectUrl && !error && (
        <div className="flex h-[40vh] items-center justify-center text-smoke">
          <CircleNotch size={28} className="animate-spin" />
        </div>
      )}
      {error && (
        <div className="flex h-[40vh] flex-col items-center justify-center gap-3">
          <p className="text-sm text-slatey">{error}</p>
          <button
            type="button"
            onClick={handleDownload}
            className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
          >
            다운로드
          </button>
        </div>
      )}
      {objectUrl && kind === 'image' && (
        <div className="rounded-lg bg-elevate p-2">
          <img
            src={objectUrl}
            alt={doc?.title ?? '문서 미리보기'}
            className="mx-auto max-h-[75vh] object-contain"
          />
        </div>
      )}
      {objectUrl && kind === 'pdf' && (
        <iframe
          src={objectUrl}
          className="h-[75vh] w-full rounded-lg border border-hairline"
          title={doc?.title ?? '문서 미리보기'}
        />
      )}
      {objectUrl && kind === null && (
        <p className="py-10 text-center text-sm text-slatey">
          미리보기를 지원하지 않는 형식입니다.
        </p>
      )}
    </Modal>
  )
}
