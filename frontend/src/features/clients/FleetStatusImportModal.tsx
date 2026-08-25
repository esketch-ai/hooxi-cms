// 운수사 계약대수 현황 업로드 (F3) — 원본 엑셀 + 대상 월(YYYY-MM) → 미리보기(합산·매칭) → 반영.
// 직관성: 월을 먼저 고르고 파일을 선택하면 즉시 preview(DB 무변경). 월을 바꾸면 재검증.
// 미리보기에 쓴 파일 객체를 그대로 commit해 preview↔commit 파리티 보장.
import { useEffect, useRef, useState } from 'react'
import { ArrowCounterClockwise, CircleNotch, WarningCircle } from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { FileUploader } from '../../components/FileUploader'
import { useToast } from '../../components/Toast'
import type { FleetStatusPreviewResult } from '../../types'
import { useFleetStatusCommit, useFleetStatusPreview } from './api'

interface Props {
  open: boolean
  onClose: () => void
}

function errorDetail(err: unknown): string | undefined {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail
  return typeof detail === 'string' ? detail : undefined
}

/** 기본 대상 월 — 전월(발행 데이터는 통상 지난달 기준). YYYY-MM. */
function defaultPeriod(): string {
  const d = new Date()
  d.setDate(1)
  d.setMonth(d.getMonth() - 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export function FleetStatusImportModal({ open, onClose }: Props) {
  const { showToast } = useToast()
  const previewMut = useFleetStatusPreview()
  const commitMut = useFleetStatusCommit()

  const [period, setPeriod] = useState(defaultPeriod)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<FleetStatusPreviewResult | null>(null)
  const latestReqRef = useRef<File | null>(null)

  useEffect(() => {
    if (open) {
      latestReqRef.current = null
      setPeriod(defaultPeriod())
      setFile(null)
      setPreview(null)
    }
  }, [open])

  const step: 'upload' | 'preview' = preview ? 'preview' : 'upload'

  const runPreview = (selected: File, forPeriod: string) => {
    latestReqRef.current = selected
    previewMut.mutate(
      { file: selected, period: forPeriod },
      {
        onSuccess: (res, sent) => {
          if (latestReqRef.current === sent.file) setPreview(res)
        },
        onError: (err, sent) => {
          if (latestReqRef.current !== sent.file) return
          setPreview(null)
          showToast(errorDetail(err) ?? '파일 검증에 실패했습니다.', 'danger')
        },
      },
    )
  }

  const handleFile = (selected: File | null) => {
    latestReqRef.current = selected
    setFile(selected)
    setPreview(null)
    if (selected) runPreview(selected, period)
  }

  const handlePeriodChange = (v: string) => {
    setPeriod(v)
    setPreview(null)
    if (file && /^\d{4}-(0[1-9]|1[0-2])$/.test(v)) runPreview(file, v)
  }

  const handleBack = () => {
    latestReqRef.current = null
    setFile(null)
    setPreview(null)
  }

  const handleCommit = () => {
    if (!file) return
    commitMut.mutate(
      { file, period },
      {
        onSuccess: (r) => {
          showToast(
            `${r.period} 반영 — 신규 ${r.created} · 갱신 ${r.updated}건${r.reconciled ? ` · 보류정합 ${r.reconciled}건` : ''} · 미매칭 ${r.unmatched}건.`,
            'success',
          )
          onClose()
        },
        onError: (err) => {
          showToast(errorDetail(err) ?? '현황 반영에 실패했습니다.', 'danger')
        },
      },
    )
  }

  const footer =
    step === 'preview' && preview ? (
      <>
        <button
          type="button"
          onClick={handleBack}
          disabled={commitMut.isPending}
          className="flex items-center gap-1.5 rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate disabled:opacity-50"
        >
          <ArrowCounterClockwise size={15} />
          다른 파일 선택
        </button>
        <button
          type="button"
          onClick={handleCommit}
          disabled={commitMut.isPending}
          className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
        >
          {commitMut.isPending && <CircleNotch size={15} className="animate-spin" />}
          {period} 반영
        </button>
      </>
    ) : undefined

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="운수사 계약대수 현황 업로드"
      size="xl"
      footer={footer}
    >
      <div className="space-y-4">
        {/* 대상 월 — 파일과 함께 (고객사×월) 스냅샷으로 저장. 같은 월 재업로드는 덮어씀 */}
        <div className="rounded-2xl border border-hairline bg-elevate p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-bone">대상 월</h3>
              <p className="mt-0.5 text-xs text-slatey">
                원본 탭의 데이터를 지정한 월(YYYY-MM) 스냅샷으로 저장 · 같은 월 재업로드는
                대수만 갱신(중복 없음)
              </p>
            </div>
            <input
              type="month"
              value={period}
              onChange={(e) => handlePeriodChange(e.target.value)}
              className="rounded-full border border-hairline bg-surface px-3.5 py-2 text-sm text-bone"
            />
          </div>
        </div>

        {step === 'upload' && (
          <>
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
          </>
        )}

        {step === 'preview' && preview && (
          <div className="space-y-3">
            <p className="text-sm">
              <span className="text-ash">원본 </span>
              <span className="text-2xl font-bold tracking-tight text-bone">
                {preview.total_rows}
              </span>
              <span className="text-ash">
                행 → 합산 <span className="font-semibold text-bone">{preview.aggregated}</span>{' '}
                · 매칭 <span className="font-semibold text-emerald-500">{preview.matched}</span> ·
                미매칭{' '}
                <span
                  className={
                    preview.unmatched > 0
                      ? 'font-semibold text-amber-400'
                      : 'font-semibold text-bone'
                  }
                >
                  {preview.unmatched}
                </span>
              </span>
            </p>

            {preview.unmatched > 0 && (
              <div className="flex items-start gap-2 rounded-xl border border-amber-400/25 bg-amber-500/15 px-3 py-2.5 text-xs text-amber-700 dark:text-amber-300">
                <WarningCircle size={15} weight="fill" className="mt-0.5 shrink-0" />
                <span>
                  미매칭 {preview.unmatched}건은 고객사 없이 보류로 저장됩니다(지역·회사명이
                  고객사 마스터와 일치하면 자동 연결). 반영 후에도 데이터는 보존됩니다.
                </span>
              </div>
            )}

            <div className="max-h-[340px] overflow-y-auto rounded-xl border border-hairline">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-elevate text-xs text-ash">
                  <tr>
                    <th className="px-3 py-2 font-medium">지역</th>
                    <th className="px-3 py-2 font-medium">회사명</th>
                    <th className="px-3 py-2 text-right font-medium">면허대수</th>
                    <th className="px-3 py-2 text-right font-medium">전기</th>
                    <th className="px-3 py-2 font-medium">매칭</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {preview.items.map((it, i) => (
                    <tr key={`${it.region}-${it.company_name}-${i}`}>
                      <td className="px-3 py-2 text-slatey">{it.region ?? '—'}</td>
                      <td className="max-w-[200px] truncate px-3 py-2 text-bone">
                        {it.company_name ?? '—'}
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums text-bone">
                        {it.license}
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums text-emerald-500">
                        {it.electric}
                      </td>
                      <td className="px-3 py-2 text-xs">
                        {it.matched ? (
                          <span className="text-emerald-500">
                            {it.is_update ? '갱신' : '연결'}
                            {it.matched_client_name ? ` · ${it.matched_client_name}` : ''}
                          </span>
                        ) : (
                          <span className="text-amber-400">보류</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}
