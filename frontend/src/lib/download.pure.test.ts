// download.ts는 지시상 '제외 모듈'(DOM 의존)이나, 아래 3개는 순수 함수라 node에서 검증 가능하다.
// (downloadBlob·downloadDocument·fetchDocumentBlob은 document/api 의존이라 제외 — 여기서 호출하지 않음)
import { AxiosError, AxiosHeaders } from 'axios'
import { describe, expect, it } from 'vitest'
import { downloadErrorMessage, previewKind, previewMimeType } from './download'

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

describe('downloadErrorMessage', () => {
  it('404 → 파일 유실 안내', () => {
    expect(downloadErrorMessage(axiosErrWithStatus(404))).toBe(
      '파일을 찾을 수 없습니다. 저장소에서 삭제되었을 수 있습니다.',
    )
  })
  it('그 외/비-Axios → 일반 실패 문구', () => {
    expect(downloadErrorMessage(axiosErrWithStatus(500))).toBe('다운로드에 실패했습니다.')
    expect(downloadErrorMessage(new Error('x'))).toBe('다운로드에 실패했습니다.')
  })
})

describe('previewKind', () => {
  it('이미지 확장자 → image (file_url 우선)', () => {
    expect(previewKind({ file_url: 'reports/ab12cd34_사진.PNG' })).toBe('image')
    expect(previewKind({ file_url: 'x/y_z.jpeg' })).toBe('image')
  })
  it('pdf → pdf', () => {
    expect(previewKind({ file_url: 'docs/uuid_계약서.pdf' })).toBe('pdf')
  })
  it('file_url 없으면 title로 폴백', () => {
    expect(previewKind({ file_url: null, title: '메모.gif' })).toBe('image')
  })
  it('확장자 없음·미지원 → null', () => {
    expect(previewKind({ file_url: 'noext' })).toBeNull()
    expect(previewKind({ file_url: 'a/b_c.docx' })).toBeNull()
    expect(previewKind({})).toBeNull()
  })
})

describe('previewMimeType', () => {
  it('알려진 확장자 → 해당 MIME', () => {
    expect(previewMimeType({ file_url: 'a_b.png' })).toBe('image/png')
    expect(previewMimeType({ file_url: 'a_b.jpg' })).toBe('image/jpeg')
    expect(previewMimeType({ file_url: 'a_b.pdf' })).toBe('application/pdf')
  })
  it('미지원/확장자 없음 → octet-stream', () => {
    expect(previewMimeType({ file_url: 'a_b.docx' })).toBe('application/octet-stream')
    expect(previewMimeType({ title: 'noext' })).toBe('application/octet-stream')
  })
})
