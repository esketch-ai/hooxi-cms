// 인증 필요한 문서 다운로드 — GET /documents/{doc_id}/download (JWT 헤더 필요, <a href> 불가)
import { api } from './api/client'

export async function downloadDocument(docId: string, filename?: string): Promise<void> {
  const { data } = await api.get(`/documents/${docId}/download`, {
    responseType: 'blob',
    timeout: 60_000,
  })
  const url = URL.createObjectURL(data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename || 'document'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
