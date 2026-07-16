// 인증 필요한 문서 다운로드 — GET /documents/{doc_id}/download (JWT 헤더 필요, <a href> 불가)
import { isAxiosError } from 'axios'
import { api } from './api/client'

/** 다운로드 실패 사용자 안내 문구 — 404(파일 유실)와 그 외(네트워크·5xx) 구분 */
export function downloadErrorMessage(err: unknown): string {
  if (isAxiosError(err) && err.response?.status === 404) {
    return '파일을 찾을 수 없습니다. 저장소에서 삭제되었을 수 있습니다.'
  }
  return '다운로드에 실패했습니다.'
}

/** 문서 파일을 Blob으로 조회 — 다운로드·미리보기 공용. 실패 시 AxiosError를 그대로 throw */
export async function fetchDocumentBlob(docId: string): Promise<Blob> {
  const { data } = await api.get(`/documents/${docId}/download`, {
    responseType: 'blob',
    timeout: 60_000,
  })
  return data as Blob
}

/** 미리보기 가능한 파일 종류 — 확장자 기준(file_url 우선, 없으면 title 폴백), 불가하면 null */
export function previewKind(doc: {
  file_url?: string | null
  title?: string | null
}): 'image' | 'pdf' | null {
  // file_url 형식: {folder}/{uuid8}_{원본파일명} — 마지막 `.` 뒤가 확장자
  const name = doc.file_url || doc.title || ''
  const dot = name.lastIndexOf('.')
  if (dot < 0) return null
  const ext = name.slice(dot + 1).toLowerCase()
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext)) return 'image'
  if (ext === 'pdf') return 'pdf'
  return null
}

/** 확장자→MIME — 리다이렉트 응답이 octet-stream일 수 있어 Blob 재래핑용 */
export function previewMimeType(doc: {
  file_url?: string | null
  title?: string | null
}): string {
  const name = doc.file_url || doc.title || ''
  const ext = name.slice(name.lastIndexOf('.') + 1).toLowerCase()
  const mimes: Record<string, string> = {
    png: 'image/png',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    gif: 'image/gif',
    webp: 'image/webp',
    svg: 'image/svg+xml',
    pdf: 'application/pdf',
  }
  return mimes[ext] ?? 'application/octet-stream'
}

/** 실패(404/503 등) 시 AxiosError를 그대로 throw — 호출처에서 catch해 토스트 표시 */
export async function downloadDocument(docId: string, filename?: string): Promise<void> {
  const data = await fetchDocumentBlob(docId)
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = filename || 'document'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
