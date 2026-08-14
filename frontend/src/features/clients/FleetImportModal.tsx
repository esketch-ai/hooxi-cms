// 전국 버스 명부 업로드 모달 (부록 M) — 안내+양식 → 파일 선택 → 미리보기(행별 검증) → 반영
// 직관성 원칙: 파일 선택 즉시 preview로 실시간 카운트(DB 무변경), 건너뜀 행은 사유를
// 한국어로 그대로 보여준다. 미리보기에 쓴 파일 객체를 반영 단계에서 그대로 재전송해
// preview↔import 파리티를 보장한다(재선택 불필요).
import { useEffect, useRef, useState } from 'react'
import {
  ArrowCounterClockwise,
  CircleNotch,
  DownloadSimple,
  WarningCircle,
} from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { FileUploader } from '../../components/FileUploader'
import { useToast } from '../../components/Toast'
import type { FleetPreviewResult } from '../../types'
import { useFleetPreview, useFleetTemplate, useImportFleet } from './api'

interface FleetImportModalProps {
  open: boolean
  onClose: () => void
  /** useImportFleet 무효화용(전역 fleet라 clients 전체 무효화, 해당 운수사 상세까지) */
  clientId?: string
}

/** 서버 detail 우선 안내 — 문자열이 아니면 무시 */
function errorDetail(err: unknown): string | undefined {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail
  return typeof detail === 'string' ? detail : undefined
}

export function FleetImportModal({ open, onClose, clientId }: FleetImportModalProps) {
  const { showToast } = useToast()
  const templateMut = useFleetTemplate()
  const previewMut = useFleetPreview()
  const importFleet = useImportFleet(clientId)

  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<FleetPreviewResult | null>(null)
  // 가장 최근 선택 파일 — 늦게 도착한 preview 응답이 최신 선택과 다르면 무시(표시-반영 일관성)
  const latestReqRef = useRef<File | null>(null)

  // 열 때마다 초기화 — 이전 세션의 파일·미리보기가 남지 않게
  useEffect(() => {
    if (open) {
      latestReqRef.current = null
      setFile(null)
      setPreview(null)
    }
  }, [open])

  // 단계는 데이터에서 파생 — 미리보기 결과가 있으면 미리보기, 아니면 안내+선택
  const step: 'upload' | 'preview' = preview ? 'preview' : 'upload'

  const handleFile = (selected: File | null) => {
    latestReqRef.current = selected
    setFile(selected)
    setPreview(null)
    if (!selected) return
    // 선택 즉시 검증 — 실시간 피드백 (DB 무변경)
    previewMut.mutate(selected, {
      // 파일을 바꿔 올린 사이 이전 요청이 늦게 도착하면 무시 (표시-반영 불일치 방지)
      onSuccess: (res, sent) => {
        if (latestReqRef.current === sent) setPreview(res)
      },
      onError: (err, sent) => {
        // 파일을 이미 바꿨거나 비웠으면 헛토스트 방지 (표시-반영 일관성)
        if (latestReqRef.current !== sent) return
        setFile(null)
        showToast(errorDetail(err) ?? '파일 검증에 실패했습니다.', 'danger')
      },
    })
  }

  // 다른 파일로 다시 시도 — 미리보기 초기화
  const handleBack = () => {
    latestReqRef.current = null
    setFile(null)
    setPreview(null)
  }

  const handleTemplate = () => {
    templateMut.mutate(undefined, {
      onError: (err) => {
        showToast(
          err instanceof Error ? err.message : '양식 다운로드에 실패했습니다.',
          'danger',
        )
      },
    })
  }

  // 반영 — 미리보기에 쓴 file 객체를 그대로 commit (preview↔import 파리티)
  const handleCommit = () => {
    if (!file) return
    importFleet.mutate(file, {
      onSuccess: (r) => {
        const tail = r.skipped > 0 ? ` · 건너뜀 ${r.skipped}건` : ''
        showToast(
          r.created + r.updated > 0
            ? `신규 ${r.created} · 갱신 ${r.updated}대 · 운수사매칭 ${r.client_matched} · 참여연결 ${r.linked_participation}${tail}.`
            : `반영된 차량이 없습니다${tail}. 양식·값을 확인해 주세요.`,
          r.created + r.updated > 0 ? 'success' : 'info',
        )
        onClose()
      },
      onError: (err) => {
        showToast(errorDetail(err) ?? '명부 업로드에 실패했습니다.', 'danger')
      },
    })
  }

  const footer =
    step === 'preview' && preview ? (
      <>
        <button
          type="button"
          onClick={handleBack}
          disabled={importFleet.isPending}
          className="flex items-center gap-1.5 rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate disabled:opacity-50"
        >
          <ArrowCounterClockwise size={15} />
          다른 파일 선택
        </button>
        <button
          type="button"
          onClick={handleCommit}
          disabled={importFleet.isPending}
          className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
        >
          {importFleet.isPending && <CircleNotch size={15} className="animate-spin" />}
          반영
        </button>
      </>
    ) : undefined

  return (
    <Modal open={open} onClose={onClose} title="전국 버스 명부 업로드" size="xl" footer={footer}>
      {step === 'upload' && (
        <div className="space-y-4">
          {/* 안내 + 양식 다운로드 */}
          <div className="rounded-2xl border border-hairline bg-elevate p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-bone">양식 안내</h3>
                <p className="mt-0.5 text-xs text-slatey">
                  BUS_LIST_ALL 시트에 입력 · 차량번호는 필수
                  <span className="text-rose-400">*</span> · 차대번호 기준 업서트(재업로드 시
                  기존 차량은 갱신)
                </p>
              </div>
              <button
                type="button"
                onClick={handleTemplate}
                disabled={templateMut.isPending}
                className="flex items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate-strong disabled:opacity-50"
              >
                {templateMut.isPending ? (
                  <CircleNotch size={15} className="animate-spin" />
                ) : (
                  <DownloadSimple size={15} />
                )}
                양식 다운로드
              </button>
            </div>
          </div>

          {/* 파일 선택 — 선택 즉시 검증(미리보기) */}
          <FileUploader
            file={file}
            onChange={handleFile}
            accept=".xlsx"
            disabled={previewMut.isPending}
          />
          {previewMut.isPending && (
            <p className="flex items-center gap-1.5 text-sm text-ash">
              <CircleNotch size={15} className="animate-spin" />
              파일을 검증하는 중… (아직 반영되지 않습니다)
            </p>
          )}
        </div>
      )}

      {step === 'preview' && preview && (
        <div className="space-y-3">
          {/* 카운트 요약 — 세그먼트 미리보기 관용구 */}
          <p className="text-sm">
            <span className="text-ash">총 </span>
            <span className="text-2xl font-bold tracking-tight text-bone">
              {preview.total_rows}
            </span>
            <span className="text-ash">
              행 · 신규 <span className="font-semibold text-bone">{preview.created}</span> · 갱신{' '}
              <span className="font-semibold text-bone">{preview.updated}</span> · 건너뜀{' '}
              <span
                className={preview.skipped > 0 ? 'font-semibold text-amber-400' : 'font-semibold text-bone'}
              >
                {preview.skipped}
              </span>{' '}
              · 운수사매칭 <span className="font-semibold text-bone">{preview.client_matched}</span>
            </span>
          </p>

          {preview.rows.length > 0 ? (
            <>
              <div className="flex items-start gap-2 rounded-xl border border-amber-400/25 bg-amber-500/15 px-3 py-2.5 text-xs text-amber-700 dark:text-amber-300">
                <WarningCircle size={15} weight="fill" className="mt-0.5 shrink-0" />
                <span>
                  아래 {preview.skipped}건은 건너뜁니다. 신규 {preview.created}·갱신{' '}
                  {preview.updated}건은 반영됩니다.
                </span>
              </div>
              <div className="max-h-[320px] overflow-y-auto rounded-xl border border-hairline">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 bg-elevate text-xs text-ash">
                    <tr>
                      <th className="px-3 py-2 font-medium">행</th>
                      <th className="px-3 py-2 font-medium">차량번호</th>
                      <th className="px-3 py-2 font-medium">사유</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {preview.rows.map((r) => (
                      <tr key={r.row}>
                        <td className="px-3 py-2 font-mono text-xs text-slatey">{r.row}</td>
                        <td className="max-w-[160px] truncate px-3 py-2 text-bone">
                          {r.vehicle_no ?? <span className="text-slatey">—</span>}
                        </td>
                        <td className="px-3 py-2 text-xs text-rose-700 dark:text-rose-300">
                          {r.reason ?? '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="rounded-lg border border-hairline bg-elevate px-3 py-2 text-xs text-ash">
              건너뛰는 행이 없습니다 — [반영]을 누르면 신규 {preview.created}·갱신{' '}
              {preview.updated}건이 반영됩니다.
            </p>
          )}
        </div>
      )}
    </Modal>
  )
}
