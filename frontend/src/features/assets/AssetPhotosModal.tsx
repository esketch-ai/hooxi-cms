// SCR-04 자산별 사진 목록 — GET /documents?asset_id= 소비부 (HistoryAttachments 관용구 준용)
// 열람은 사무실 PC에서도 필요하므로 터치 게이트 없이 모든 기기에서 진입, 목록은 모달 오픈 시에만 조회
import { useState } from 'react'
import { CircleNotch, DownloadSimple, Images, Trash } from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { DocumentPreviewModal } from '../../components/DocumentPreviewModal'
import { useToast } from '../../components/Toast'
import { useAssetDocuments, useDeleteDocument } from '../../lib/api/queries'
import { downloadDocument, downloadErrorMessage, previewKind } from '../../lib/download'
import { fmtServerDateTime } from '../../lib/format'
import type { Asset, Document } from '../../types'
import { assetDisplayName } from './SpecPhotoModal'

export function AssetPhotosModal({
  asset,
  onClose,
}: {
  /** 대상 자산 — null이면 닫힘 */
  asset: Asset | null
  onClose: () => void
}) {
  const { showToast } = useToast()
  // enabled 게이트 — 모달이 열려 asset이 있을 때만 조회 (목록 화면 과호출 방지)
  const { data: docs = [], isLoading, isError } = useAssetDocuments(asset?.asset_id)
  // 제목 클릭 → 미리보기(이미지/PDF만) — 사진 모달 위에 미리보기 모달 중첩(DOM 후순위로 최상단)
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null)
  const [deleteDoc, setDeleteDoc] = useState<Document | null>(null)
  const deleteDocument = useDeleteDocument()

  const handleDownload = async (docId: string, title?: string) => {
    try {
      await downloadDocument(docId, title)
    } catch (err) {
      showToast(downloadErrorMessage(err), 'danger')
    }
  }

  return (
    <>
      <Modal open={asset != null} onClose={onClose} title="자산 사진" size="md">
        <div className="space-y-3">
          {asset && (
            <p className="text-xs text-slatey">
              {asset.client_name ?? '고객사'} ·{' '}
              <span className="text-ash">{assetDisplayName(asset)}</span> 자산에 연결된 현장
              사진입니다.
            </p>
          )}
          {isLoading ? (
            <div className="flex items-center justify-center gap-2 py-6 text-sm text-slatey">
              <CircleNotch size={16} className="animate-spin" />
              사진 목록을 불러오는 중…
            </div>
          ) : isError ? (
            <p className="py-6 text-center text-sm text-slatey">
              사진 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.
            </p>
          ) : docs.length === 0 ? (
            <div className="flex flex-col items-center gap-1.5 py-6 text-center">
              <Images size={28} className="text-slatey" />
              <p className="text-sm text-slatey">등록된 사진이 없습니다</p>
              <p className="text-xs text-slatey">
                태블릿의 [제원표 촬영]으로 현장에서 첨부할 수 있습니다.
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-hairline">
              {docs.map((d) => (
                <li key={d.doc_id} className="flex items-center justify-between gap-2 py-2">
                  <div className="min-w-0">
                    {previewKind(d) ? (
                      <button
                        type="button"
                        onClick={() => setPreviewDoc(d)}
                        className="block max-w-full truncate text-left text-sm text-bone hover:underline"
                        title="미리보기"
                      >
                        {d.title}
                      </button>
                    ) : (
                      <p className="truncate text-sm text-bone">{d.title}</p>
                    )}
                    <p className="text-xs text-slatey">{fmtServerDateTime(d.created_at)}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      onClick={() => void handleDownload(d.doc_id, d.title)}
                      className="rounded-lg p-1.5 text-smoke hover:bg-elevate hover:text-bone"
                      title="다운로드"
                      aria-label={`${d.title} 다운로드`}
                    >
                      <DownloadSimple size={16} />
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleteDoc(d)}
                      className="rounded-lg p-1.5 text-smoke hover:bg-rose-500/10 hover:text-rose-400"
                      title="삭제"
                      aria-label={`${d.title} 삭제`}
                    >
                      <Trash size={16} />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <div className="flex justify-end border-t border-hairline pt-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
            >
              닫기
            </button>
          </div>
        </div>
      </Modal>
      {/* 사진 모달 위 미리보기 — 동일 z-50이지만 DOM 후순위라 최상단에 겹침 */}
      <DocumentPreviewModal doc={previewDoc} onClose={() => setPreviewDoc(null)} />
      <ConfirmDialog
        open={!!deleteDoc}
        title="사진 삭제"
        message={
          <>
            <b>{deleteDoc?.title}</b> 사진을 삭제합니다. 되돌릴 수 없습니다.
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
            showToast('사진이 삭제되었습니다.', 'success')
            setDeleteDoc(null)
          } catch (err) {
            const detail = (err as { response?: { data?: { detail?: string } } })?.response
              ?.data?.detail
            showToast(detail || '삭제에 실패했습니다.', 'danger')
          }
        }}
      />
    </>
  )
}
