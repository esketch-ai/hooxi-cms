// 고객사 Dropbox 폴더 라이브 브라우즈 파일 피커 — 발송 첨부 선택용 (방식 A).
// 폴더 네비게이션(브레드크럼·상위로), 파일 다중 선택. 경로는 서버가 고객사 폴더로 confinement.
import { CaretUp, CircleNotch, File as FileIcon, Folder } from '@phosphor-icons/react'
import { isAxiosError } from 'axios'
import { useEffect, useState } from 'react'
import { useDropboxTree } from '../lib/api/queries'
import { Modal } from './Modal'

interface DropboxPickerProps {
  open: boolean
  // 조회 엔드포인트 — 고객사 폴더(`/clients/{id}/dropbox/tree`) 또는 공용(`/segments/dropbox/tree`)
  endpoint: string | null | undefined
  initialSelected?: string[]
  onClose: () => void
  onConfirm: (paths: string[]) => void
}

function parentOf(path: string): string {
  const parent = path.replace(/\/[^/]*$/, '')
  return parent || '/'
}

function errorMessage(err: unknown): string {
  if (isAxiosError(err)) {
    const status = err.response?.status
    const detail = (err.response?.data as { detail?: string } | undefined)?.detail
    if (status === 409) return detail ?? '이 고객사는 아직 Dropbox 폴더가 없습니다.'
    if (status === 503) return detail ?? 'Dropbox 연동이 설정되지 않았습니다.'
    if (status === 403) return detail ?? '접근할 수 없는 경로입니다.'
    if (status === 404) return detail ?? '폴더를 찾을 수 없습니다.'
    return detail ?? '폴더를 불러오지 못했습니다.'
  }
  return '폴더를 불러오지 못했습니다.'
}

export function DropboxPicker({
  open,
  endpoint,
  initialSelected,
  onClose,
  onConfirm,
}: DropboxPickerProps) {
  const [path, setPath] = useState<string | null>(null) // null = 루트
  const [rootPath, setRootPath] = useState<string | null>(null)
  const [selected, setSelected] = useState<string[]>([])

  // 열릴 때마다 초기화 — 기존 확정 선택으로 시드(재오픈 시 배지와 체크박스 일치)
  useEffect(() => {
    if (open) {
      setPath(null)
      setRootPath(null)
      setSelected(initialSelected ?? [])
    }
    // initialSelected는 open 시점 값만 사용 — 의존성에서 제외
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, endpoint])

  const { data, isLoading, isError, error } = useDropboxTree(open ? endpoint ?? null : null, path)

  // 첫 응답의 경로를 고객사 루트로 기억(상위로 이동 하한)
  useEffect(() => {
    if (data && rootPath === null) setRootPath(data.path)
  }, [data, rootPath])

  const currentPath = data?.path ?? ''
  const atRoot = !rootPath || currentPath === rootPath

  const toggle = (p: string) =>
    setSelected((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]))

  const goUp = () => {
    if (atRoot) return
    const parent = parentOf(currentPath)
    setPath(rootPath && parent.length < rootPath.length ? rootPath : parent)
  }

  return (
    <Modal open={open} onClose={onClose} title="Dropbox에서 첨부 파일 선택" size="lg">
      <div className="space-y-3">
        {/* 브레드크럼 + 상위로 */}
        <div className="flex items-center gap-2 text-xs text-slatey">
          <button
            type="button"
            onClick={goUp}
            disabled={atRoot}
            className="flex items-center gap-1 rounded-full border border-hairline px-2.5 py-1 text-bone hover:bg-elevate disabled:opacity-40"
          >
            <CaretUp size={13} /> 상위로
          </button>
          <span className="truncate font-mono text-ash">{currentPath || '…'}</span>
        </div>

        {/* 목록 */}
        <div className="max-h-80 overflow-y-auto rounded-2xl border border-hairline">
          {isLoading ? (
            <div className="flex items-center justify-center gap-2 py-10 text-sm text-slatey">
              <CircleNotch size={16} className="animate-spin" /> 불러오는 중…
            </div>
          ) : isError ? (
            <div className="px-4 py-10 text-center text-sm text-slatey">{errorMessage(error)}</div>
          ) : !data || data.entries.length === 0 ? (
            <div className="px-4 py-10 text-center text-sm text-slatey">이 폴더는 비어 있습니다.</div>
          ) : (
            <ul className="divide-y divide-hairline">
              {data.entries.map((e) =>
                e.is_dir ? (
                  <li key={e.path_display}>
                    <button
                      type="button"
                      onClick={() => setPath(e.path_display)}
                      className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm text-bone hover:bg-elevate"
                    >
                      <Folder size={16} weight="fill" className="text-slatey" />
                      <span className="truncate">{e.name}</span>
                    </button>
                  </li>
                ) : (
                  <li key={e.path_display}>
                    <label className="flex cursor-pointer items-center gap-2.5 px-3 py-2.5 text-sm text-bone hover:bg-elevate">
                      <input
                        type="checkbox"
                        checked={selected.includes(e.path_display)}
                        onChange={() => toggle(e.path_display)}
                      />
                      <FileIcon size={16} className="text-slatey" />
                      <span className="truncate">{e.name}</span>
                    </label>
                  </li>
                ),
              )}
            </ul>
          )}
        </div>

        {/* 액션 */}
        <div className="flex items-center justify-between border-t border-hairline pt-3">
          <span className="text-xs text-slatey">{selected.length}개 선택됨</span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
            >
              취소
            </button>
            <button
              type="button"
              disabled={selected.length === 0}
              onClick={() => onConfirm(selected)}
              className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-60"
            >
              첨부 확정
            </button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
