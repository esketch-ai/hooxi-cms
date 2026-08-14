import { AxiosError, AxiosHeaders } from 'axios'
import { describe, expect, it } from 'vitest'
import { exportErrorMessage } from './export'

// 상태코드별 안내 문구 매핑만 검증 — downloadExport(api+DOM 의존)는 대상 아님
function axiosErrWithStatus(status: number): AxiosError {
  const err = new AxiosError('boom')
  err.response = {
    status,
    statusText: '',
    data: {},
    headers: {},
    config: { headers: new AxiosHeaders() },
  }
  return err
}

describe('exportErrorMessage', () => {
  it('403 → 권한 안내', () => {
    expect(exportErrorMessage(axiosErrWithStatus(403))).toBe('내보내기 권한이 없습니다(팀장 이상).')
  })
  it('429 → 한도 초과 안내', () => {
    expect(exportErrorMessage(axiosErrWithStatus(429))).toBe('오늘 내보내기 한도를 초과했습니다.')
  })
  it('400 → 행 상한 안내', () => {
    expect(exportErrorMessage(axiosErrWithStatus(400))).toBe('행이 많습니다 — 필터를 좁혀 주세요.')
  })
  it('그 외 상태코드(500) → 일반 실패 문구', () => {
    expect(exportErrorMessage(axiosErrWithStatus(500))).toBe('내보내기에 실패했습니다.')
  })
  it('AxiosError가 아니면 일반 실패 문구', () => {
    expect(exportErrorMessage(new Error('generic'))).toBe('내보내기에 실패했습니다.')
    expect(exportErrorMessage(null)).toBe('내보내기에 실패했습니다.')
  })
})
