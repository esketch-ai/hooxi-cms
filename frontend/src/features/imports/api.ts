// 엑셀 일괄 등록 API 훅 (SCR-03·04 공용) — backend/routers/imports.py 대응
// preview는 DB 무변경, commit은 같은 파일 재검증 후 유효 행만 부분 반영
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api/client'
import type {
  ImportCommitResult,
  ImportEntity,
  ImportPreview,
  ImportSpec,
} from '../../types'

/** 컬럼 안내 — GET /imports/{entity}/spec (모달 열림 시에만 조회) */
export function useImportSpec(entity: ImportEntity, enabled = true) {
  return useQuery({
    queryKey: ['imports', entity, 'spec'],
    queryFn: async () => {
      const { data } = await api.get<ImportSpec>(`/imports/${entity}/spec`)
      return data
    },
    enabled,
    staleTime: 5 * 60_000, // 규격은 코드 라벨 변경 외엔 고정 — 재열람 깜빡임 방지
  })
}

/** 양식(.xlsx) 다운로드 — 응답 헤더 파일명(RFC 5987) 우선, 실패 시 throw (lib/download.ts 관용구) */
export async function downloadImportTemplate(
  entity: ImportEntity,
  fallbackName?: string,
): Promise<void> {
  const res = await api.get(`/imports/${entity}/template`, {
    responseType: 'blob',
    timeout: 60_000,
  })
  const disposition = (res.headers['content-disposition'] as string | undefined) ?? ''
  const match = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  const filename = match
    ? decodeURIComponent(match[1])
    : fallbackName ?? `${entity}_import.xlsx`
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** 미리보기 — POST /imports/{entity}/preview (multipart, DB 무변경) */
export function useImportPreview(entity: ImportEntity) {
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      const { data } = await api.post<ImportPreview>(`/imports/${entity}/preview`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60_000,
      })
      return data
    },
  })
}

/** 반영 — POST /imports/{entity}/commit (동일 파일, 유효 행만 부분 반영) */
export function useImportCommit(entity: ImportEntity) {
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      const { data } = await api.post<ImportCommitResult>(`/imports/${entity}/commit`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60_000,
      })
      return data
    },
  })
}
