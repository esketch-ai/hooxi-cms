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

/** 실패(404/503 등) 시 AxiosError를 그대로 throw — 호출처에서 catch해 토스트 표시 */
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
