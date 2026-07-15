// SCR-04 제원표 촬영 첨부 — 태블릿 현장에서 자산 제원표를 촬영해 고객사 문서함(PHOTO)에 업로드
// 제목 규약: 제원표_{자산명}_{YYYY-MM-DD} (KST 기준 오늘)
import { useState, type FormEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CircleNotch } from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { FileUploader } from '../../components/FileUploader'
import { useToast } from '../../components/Toast'
import { api } from '../../lib/api/client'
import { todayKst } from '../../lib/format'
import type { Asset } from '../../types'

/** 자산 표시명 — AssetSpecCell과 동일 폴백 (main_spec 없으면 대분류 기본명) */
export function assetDisplayName(asset: Asset): string {
  return asset.main_spec ?? (asset.asset_group === 'MOBILITY' ? '차량' : '설비')
}

export function SpecPhotoModal({
  asset,
  onClose,
}: {
  /** 대상 자산 — null이면 닫힘 */
  asset: Asset | null
  onClose: () => void
}) {
  const { showToast } = useToast()
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)

  const upload = useMutation({
    mutationFn: async () => {
      if (!asset || !file) return
      const form = new FormData()
      form.append('file', file)
      form.append('title', `제원표_${assetDisplayName(asset)}_${todayKst()}`)
      form.append('doc_type', 'PHOTO')
      form.append('client_id', asset.client_id)
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

  const handleClose = () => {
    setFile(null)
    onClose()
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!file) {
      showToast('제원표 사진을 촬영하거나 선택해 주세요.', 'danger')
      return
    }
    try {
      await upload.mutateAsync()
      showToast('제원표 사진이 문서함에 업로드되었습니다.', 'success')
      handleClose()
    } catch {
      showToast('업로드에 실패했습니다.', 'danger')
    }
  }

  return (
    <Modal open={asset != null} onClose={handleClose} title="제원표 촬영" size="md">
      <form onSubmit={handleSubmit} className="space-y-3">
        {asset && (
          <p className="text-xs text-slatey">
            {asset.client_name ?? '고객사'} 문서함(현장 사진)에{' '}
            <span className="font-mono text-ash">
              제원표_{assetDisplayName(asset)}_{todayKst()}
            </span>
            으로 저장됩니다.
          </p>
        )}
        <FileUploader file={file} onChange={setFile} accept="image/*" enableCamera compressImages />
        <div className="flex justify-end gap-2 border-t border-hairline pt-3">
          <button
            type="button"
            onClick={handleClose}
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
