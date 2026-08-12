// 공용 엑셀(xlsx) 내보내기 — 현재 필터를 그대로 서버로 넘겨 전체행 파일을 받는다.
// blob 응답이라 <a href>로는 JWT 헤더가 안 실려 api.get + downloadBlob 관례를 재사용한다.
import { isAxiosError } from 'axios'
import { api } from './api/client'
import { downloadBlob } from './download'

/** 내보내기 실패 사용자 안내 문구 — 상태코드로 분기(403 권한/429 한도/400 행상한/그 외) */
export function exportErrorMessage(err: unknown): string {
  if (isAxiosError(err)) {
    const status = err.response?.status
    if (status === 403) return '내보내기 권한이 없습니다(팀장 이상).'
    if (status === 429) return '오늘 내보내기 한도를 초과했습니다.'
    if (status === 400) return '행이 많습니다 — 필터를 좁혀 주세요.'
  }
  return '내보내기에 실패했습니다.'
}

/** Content-Disposition의 filename*=UTF-8''... 를 파싱 — 없으면 fallback */
function parseFilename(disposition: unknown, fallback: string): string {
  if (typeof disposition !== 'string') return fallback
  // RFC 5987: filename*=UTF-8''%EC%9E%AC... (우선), 없으면 filename="..."
  const star = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1])
    } catch {
      return fallback
    }
  }
  const plain = disposition.match(/filename="?([^";]+)"?/i)
  return plain?.[1] ?? fallback
}

/** blob 에러 바디(JSON)에서 detail 문자열을 뽑는다 — 파싱 불가하면 null */
async function readBlobDetail(blob: Blob): Promise<string | null> {
  try {
    const detail = JSON.parse(await blob.text())?.detail
    return typeof detail === 'string' && detail ? detail : null
  } catch {
    return null
  }
}

/** 빈/undefined 파라미터 제거 — 서버에 불필요한 빈 필터를 넘기지 않는다 */
function cleanParams(params: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue
    out[k] = v
  }
  return out
}

/**
 * 현재 필터로 xlsx를 내려받는다. 실패 시 사용자 문구를 담은 Error를 throw(호출부가 토스트).
 * @param path 서버 export 엔드포인트 경로(baseURL 이하)
 * @param params 현재 필터 — 빈 값은 자동 제거
 * @param fallbackName Content-Disposition 없을 때 파일명
 */
export async function downloadExport(
  path: string,
  params: Record<string, unknown>,
  fallbackName: string,
): Promise<void> {
  try {
    const res = await api.get(path, {
      params: cleanParams(params),
      responseType: 'blob',
      timeout: 60_000,
    })
    const name = parseFilename(res.headers['content-disposition'], fallbackName)
    downloadBlob(res.data as Blob, name)
  } catch (err) {
    // blob 에러 바디에 담긴 detail을 우선 시도, 실패하면 상태코드 기반 문구로 폴백
    if (isAxiosError(err) && err.response?.data instanceof Blob) {
      const detail = await readBlobDetail(err.response.data)
      if (detail) throw new Error(detail)
    }
    throw new Error(exportErrorMessage(err))
  }
}
