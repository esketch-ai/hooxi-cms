// 엑셀 일괄 등록 모달 (SCR-03·04 공용) — 안내+양식 → 파일 선택 → 미리보기 → 반영
// 직관성 원칙: 파일 선택 즉시 preview로 실시간 카운트, 오류 행도 사유를 한국어로
// 그대로 보여줘 막다른 정보 금지. 오류가 있어도 유효 행만 부분 반영 가능(버튼에 건수 명시).
import { useEffect, useMemo, useState } from 'react'
import {
  ArrowCounterClockwise,
  CheckCircle,
  CircleNotch,
  DownloadSimple,
  WarningCircle,
} from '@phosphor-icons/react'
import { Modal } from '../../components/Modal'
import { FileUploader } from '../../components/FileUploader'
import { useToast } from '../../components/Toast'
import type {
  ImportColumn,
  ImportCommitResult,
  ImportEntity,
  ImportPreview,
  ImportRowResult,
} from '../../types'
import {
  downloadImportTemplate,
  useImportCommit,
  useImportPreview,
  useImportSpec,
} from './api'

interface ExcelImportModalProps {
  entity: ImportEntity
  open: boolean
  onClose: () => void
  /** commit이 1회라도 성공한 세션이 닫힐 때 호출 — 목록 쿼리 무효화용 */
  onDone: () => void
}

/** 422/413 등 서버 detail 우선 안내 (segments 관용구) — 문자열이 아니면 무시 */
function errorDetail(err: unknown): string | undefined {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail
  return typeof detail === 'string' ? detail : undefined
}

/** 컬럼 허용값 요약 — 고정값 > Y/N > 예시 순 */
function columnHint(col: ImportColumn): string | null {
  if (col.allowed_values?.length) return col.allowed_values.join(' / ')
  if (col.yn) return 'Y / N'
  if (col.example) return `예: ${col.example}`
  return null
}

/** 행별 결과 테이블 — 미리보기(c)·확정 후 실패 잔여(d) 공용 */
function RowResultTable({
  rows,
  keyCols,
}: {
  rows: ImportRowResult[]
  keyCols: ImportColumn[]
}) {
  return (
    <div className="max-h-[320px] overflow-y-auto rounded-xl border border-hairline">
      <table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-elevate text-xs text-ash">
          <tr>
            <th className="px-3 py-2 font-medium">행</th>
            <th className="px-3 py-2 font-medium">상태</th>
            {keyCols.map((c) => (
              <th key={c.field} className="px-3 py-2 font-medium">
                {c.label}
              </th>
            ))}
            <th className="px-3 py-2 font-medium">사유</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {rows.map((r) => (
            <tr key={r.row} className={r.status === 'ERROR' ? 'bg-rose-500/5' : ''}>
              <td className="px-3 py-2 font-mono text-xs text-slatey">{r.row}</td>
              <td className="px-3 py-2">
                {r.status === 'OK' ? (
                  <CheckCircle size={16} weight="fill" className="text-emerald-400" />
                ) : (
                  <WarningCircle size={16} weight="fill" className="text-rose-400" />
                )}
              </td>
              {keyCols.map((c) => (
                <td key={c.field} className="max-w-[160px] truncate px-3 py-2 text-bone">
                  {r.data[c.label] ?? <span className="text-slatey">—</span>}
                </td>
              ))}
              <td className="px-3 py-2">
                {r.errors.map((msg, i) => (
                  <p key={`e${i}`} className="text-xs text-rose-700 dark:text-rose-300">
                    {msg}
                  </p>
                ))}
                {r.warnings.map((msg, i) => (
                  <p key={`w${i}`} className="text-xs text-amber-700 dark:text-amber-300">
                    {msg}
                  </p>
                ))}
                {r.errors.length === 0 && r.warnings.length === 0 && (
                  <span className="text-xs text-slatey">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ExcelImportModal({ entity, open, onClose, onDone }: ExcelImportModalProps) {
  const { showToast } = useToast()
  const spec = useImportSpec(entity, open)
  const previewMut = useImportPreview(entity)
  const commitMut = useImportCommit(entity)

  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [result, setResult] = useState<ImportCommitResult | null>(null)
  const [committed, setCommitted] = useState(false) // 세션 내 반영 여부 — 닫을 때 onDone
  const [downloading, setDownloading] = useState(false)

  // 열 때마다 초기화 — 이전 세션의 파일·결과가 남지 않게
  useEffect(() => {
    if (open) {
      setFile(null)
      setPreview(null)
      setResult(null)
      setCommitted(false)
    }
  }, [open])

  // 단계는 데이터에서 파생 — (a)(b) 안내+선택 / (c) 미리보기 / (d) 확정 결과
  const step: 'upload' | 'preview' | 'done' = result ? 'done' : preview ? 'preview' : 'upload'

  // 미리보기 주요 값 컬럼 — 필수 우선 최대 3개
  const keyCols = useMemo(() => {
    const cols = spec.data?.columns ?? []
    return [...cols.filter((c) => c.required), ...cols.filter((c) => !c.required)].slice(0, 3)
  }, [spec.data])

  const handleFile = (selected: File | null) => {
    setFile(selected)
    setPreview(null)
    if (!selected) return
    // 선택 즉시 검증 — 실시간 피드백 (DB 무변경)
    previewMut.mutate(selected, {
      // 파일을 바꿔 올린 사이 이전 요청이 늦게 도착하면 무시 (표시-반영 불일치 방지)
      onSuccess: (res, sent) => {
        setFile((current) => {
          if (current === sent) setPreview(res)
          return current
        })
      },
      onError: (err) => {
        setFile(null)
        showToast(errorDetail(err) ?? '파일 검증에 실패했습니다.', 'danger')
      },
    })
  }

  const handleCommit = () => {
    if (!file) return
    commitMut.mutate(file, {
      onSuccess: (res) => {
        setResult(res)
        setCommitted(true)
        onDone() // 성공 즉시 목록 무효화 — 진행 중 모달이 닫혀도 정합 유지
      },
      onError: (err) => {
        showToast(errorDetail(err) ?? '일괄 등록에 실패했습니다.', 'danger')
      },
    })
  }

  // 뒤로가기 — 다른 파일로 다시 시도 (확정 후에도 가능)
  const handleBack = () => {
    setFile(null)
    setPreview(null)
    setResult(null)
  }

  const handleClose = () => {
    onClose() // onDone은 commit 성공 시점에 이미 호출됨 (무효화 멱등)
  }

  const handleTemplate = async () => {
    setDownloading(true)
    try {
      await downloadImportTemplate(entity, spec.data?.filename)
    } catch (err) {
      showToast(errorDetail(err) ?? '양식 다운로드에 실패했습니다.', 'danger')
    } finally {
      setDownloading(false)
    }
  }

  const footer =
    step === 'preview' && preview ? (
      <>
        <button
          type="button"
          onClick={handleBack}
          className="flex items-center gap-1.5 rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
        >
          <ArrowCounterClockwise size={15} />
          다른 파일 선택
        </button>
        <button
          type="button"
          onClick={handleCommit}
          disabled={preview.valid_rows === 0 || commitMut.isPending}
          className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90 disabled:opacity-50"
          title={
            preview.valid_rows === 0
              ? '등록 가능한 행이 없습니다 — 오류를 수정한 파일로 다시 시도하세요'
              : `오류 ${preview.error_rows}건은 건너뛰고 유효 행만 등록합니다`
          }
        >
          {commitMut.isPending && <CircleNotch size={15} className="animate-spin" />}
          {preview.valid_rows}건 등록
        </button>
      </>
    ) : step === 'done' && result ? (
      <>
        {result.skipped > 0 && (
          <button
            type="button"
            onClick={handleBack}
            className="flex items-center gap-1.5 rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate"
          >
            <ArrowCounterClockwise size={15} />
            다른 파일로 다시 등록
          </button>
        )}
        <button
          type="button"
          onClick={handleClose}
          className="rounded-full bg-primary px-4 py-2 text-sm font-medium text-on-primary hover:opacity-90"
        >
          완료
        </button>
      </>
    ) : undefined

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={`${spec.data?.label ?? ''} 엑셀 일괄 등록`.trim()}
      size="xl"
      footer={footer}
    >
      {step === 'upload' && (
        <div className="space-y-4">
          {/* (a) 안내 + 양식 다운로드 */}
          <div className="rounded-2xl border border-hairline bg-elevate p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-bone">양식 안내</h3>
                <p className="mt-0.5 text-xs text-slatey">
                  최대 {spec.data?.max_rows ?? '—'}행 · 필수 컬럼은 <span className="text-rose-400">*</span> 표시 ·
                  분류 컬럼은 아래 허용값(한국어 라벨)으로 입력
                </p>
              </div>
              <button
                type="button"
                onClick={handleTemplate}
                disabled={downloading || spec.isLoading}
                className="flex items-center gap-1.5 rounded-full border border-hairline px-3.5 py-2 text-sm font-medium text-bone hover:bg-elevate-strong disabled:opacity-50"
              >
                {downloading ? (
                  <CircleNotch size={15} className="animate-spin" />
                ) : (
                  <DownloadSimple size={15} />
                )}
                양식 다운로드
              </button>
            </div>
            {spec.isLoading ? (
              <p className="mt-3 text-xs text-slatey">컬럼 안내를 불러오는 중…</p>
            ) : spec.isError ? (
              <p className="mt-3 text-xs text-rose-700 dark:text-rose-300">
                컬럼 안내를 불러오지 못했습니다 — 양식 다운로드는 계속 시도할 수 있습니다.
              </p>
            ) : (
              <div className="mt-3 grid gap-1.5 sm:grid-cols-2">
                {(spec.data?.columns ?? []).map((c) => {
                  const hint = columnHint(c)
                  return (
                    <div
                      key={c.field}
                      className="flex items-baseline gap-2 rounded-lg bg-graphite px-2.5 py-1.5"
                    >
                      <span className="shrink-0 text-xs font-medium text-bone">
                        {c.label}
                        {c.required && <span className="ml-0.5 text-rose-400">*</span>}
                      </span>
                      {hint && <span className="truncate text-xs text-slatey" title={hint}>{hint}</span>}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* (b) 파일 선택 — 선택 즉시 검증(미리보기) */}
          <FileUploader
            file={file}
            onChange={handleFile}
            accept=".xlsx"
            disabled={previewMut.isPending}
          />
          {previewMut.isPending && (
            <p className="flex items-center gap-1.5 text-sm text-ash">
              <CircleNotch size={15} className="animate-spin" />
              파일을 검증하는 중… (아직 등록되지 않습니다)
            </p>
          )}
        </div>
      )}

      {step === 'preview' && preview && (
        <div className="space-y-3">
          {/* (c) 실시간 카운트 — 세그먼트 미리보기 관용구 */}
          <p>
            <span className="text-sm text-ash">총 {preview.total_rows}행 중</span>
            <span className="ml-2 text-4xl font-bold tracking-tight text-bone">
              {preview.valid_rows}
            </span>
            <span className="ml-1 text-sm text-ash">건 등록 가능</span>
            {preview.error_rows > 0 && (
              <span className="ml-3 text-sm font-medium text-rose-700 dark:text-rose-300">
                · {preview.error_rows}건 오류
              </span>
            )}
          </p>

          {(preview.warnings ?? []).length > 0 && (
            <p className="rounded-lg border border-hairline bg-elevate px-3 py-2 text-xs text-ash">
              {(preview.warnings ?? []).join(' · ')}
            </p>
          )}
          {preview.unknown_columns.length > 0 && (
            <div className="flex items-start gap-2 rounded-xl border border-amber-400/25 bg-amber-500/15 px-3 py-2.5 text-xs text-amber-700 dark:text-amber-300">
              <WarningCircle size={15} weight="fill" className="mt-0.5 shrink-0" />
              <span>
                양식에 없는 컬럼은 무시됩니다: {preview.unknown_columns.join(', ')}
              </span>
            </div>
          )}

          <RowResultTable rows={preview.rows} keyCols={keyCols} />

          {preview.error_rows > 0 && preview.valid_rows > 0 && (
            <p className="text-xs text-slatey">
              오류 행은 건너뛰고 유효한 {preview.valid_rows}건만 등록됩니다 — 건너뛴 행은
              사유를 수정해 다시 업로드할 수 있습니다.
            </p>
          )}
        </div>
      )}

      {step === 'done' && result && (
        <div className="space-y-3">
          {/* (d) 확정 결과 요약 */}
          <div className="flex items-center gap-2.5 rounded-2xl border border-hairline bg-elevate px-4 py-3">
            <CheckCircle size={24} weight="fill" className="shrink-0 text-emerald-400" />
            <div>
              <p className="text-sm font-semibold text-bone">
                {result.created}건 등록 완료
                {result.skipped > 0 && (
                  <span className="ml-2 font-medium text-amber-700 dark:text-amber-300">
                    · {result.skipped}건 건너뜀
                  </span>
                )}
              </p>
              <p className="text-xs text-slatey">
                {result.skipped > 0
                  ? '건너뛴 행은 아래 사유를 수정해 다른 파일로 다시 등록할 수 있습니다.'
                  : '모든 행이 등록되었습니다.'}
              </p>
            </div>
          </div>

          {result.errors.length > 0 && (
            <RowResultTable rows={result.errors} keyCols={keyCols} />
          )}
        </div>
      )}
    </Modal>
  )
}
