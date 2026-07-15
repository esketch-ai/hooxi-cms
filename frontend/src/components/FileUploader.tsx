// 파일 업로더 (플랜 §4.2) — 드래그앤드롭 + 클릭 선택, SCR-12·13 공용
import { useRef, useState, type DragEvent } from 'react'
import { Camera, CloudArrowUp, FileText, X } from '@phosphor-icons/react'
import { compressImage } from '../lib/image'
import { usePointerCoarse } from '../lib/usePointerCoarse'

interface FileUploaderProps {
  /** 선택 파일 (제어형) */
  file: File | null
  onChange: (file: File | null) => void
  accept?: string
  disabled?: boolean
  className?: string
  /**
   * 태블릿 현장용 카메라 촬영 버튼 (옵트인).
   * 터치 기기(pointer: coarse)에서만 노출되며, 촬영된 이미지는 클라이언트
   * 압축(compressImage)을 거쳐 전달된다. 미지정 시 기존 동작과 동일.
   */
  enableCamera?: boolean
  /**
   * 일반 선택(클릭·드래그앤드롭) 이미지에도 압축 적용 (옵트인).
   * 현장 사진처럼 압축이 바람직한 곳만 켠다 — 문서 아카이브 등
   * 원본 보존이 필요한 업로드에는 켜지 말 것(카메라 촬영분은 항상 압축).
   */
  compressImages?: boolean
}

export function FileUploader({
  file,
  onChange,
  accept,
  disabled = false,
  className = '',
  enableCamera = false,
  compressImages = false,
}: FileUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const cameraRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const isCoarse = usePointerCoarse()
  const showCamera = enableCamera && isCoarse

  // 촬영분은 항상, 일반 선택분은 compressImages 옵트인 시에만 압축
  // (문서 아카이브 등 원본 보존이 필요한 경로에서 무단 재인코딩 금지)
  const handleFile = (selected: File, fromCamera = false) => {
    if ((fromCamera || compressImages) && selected.type.startsWith('image/')) {
      void compressImage(selected).then(onChange)
    } else {
      onChange(selected)
    }
  }

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragOver(false)
    if (disabled) return
    const dropped = e.dataTransfer.files?.[0]
    if (dropped) handleFile(dropped)
  }

  if (file) {
    return (
      <div
        className={`flex items-center gap-2.5 rounded-lg border border-hairline bg-elevate px-3 py-2.5 ${className}`}
      >
        <FileText size={20} className="shrink-0 text-smoke" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-bone">{file.name}</p>
          <p className="text-xs text-slatey">{(file.size / 1024).toFixed(0)} KB</p>
        </div>
        <button
          type="button"
          onClick={() => onChange(null)}
          className="rounded-md p-1 text-smoke hover:bg-elevate hover:text-bone"
          aria-label="파일 제거"
        >
          <X size={16} />
        </button>
      </div>
    )
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(e) =>
        e.key === 'Enter' &&
        e.target === e.currentTarget && // 내부 촬영 버튼의 Enter 버블 제외
        !disabled &&
        inputRef.current?.click()
      }
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors ${
        dragOver ? 'border-white/30 bg-elevate' : 'border-hairline bg-graphite hover:bg-elevate'
      } ${disabled ? 'cursor-not-allowed opacity-50' : ''} ${className}`}
      aria-label="파일 업로드"
    >
      <CloudArrowUp size={28} className="mb-2 text-smoke" />
      <p className="text-sm font-medium text-ash">
        파일을 끌어다 놓거나 클릭하여 선택
      </p>
      {accept && <p className="mt-1 text-xs text-slatey">{accept}</p>}
      {showCamera && (
        <button
          type="button"
          disabled={disabled}
          onClick={(e) => {
            e.stopPropagation() // 드롭존 클릭(파일 선택)과 분리
            cameraRef.current?.click()
          }}
          className="mt-3 flex items-center gap-1.5 rounded-full border border-hairline bg-elevate px-3.5 py-1.5 text-sm font-medium text-bone hover:bg-elevate-strong"
        >
          <Camera size={16} />
          카메라 촬영
        </button>
      )}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        disabled={disabled}
        className="hidden"
        onChange={(e) => {
          const selected = e.target.files?.[0]
          if (selected) handleFile(selected)
          e.target.value = ''
        }}
      />
      {showCamera && (
        <input
          ref={cameraRef}
          type="file"
          accept="image/*"
          capture="environment"
          disabled={disabled}
          className="hidden"
          onChange={(e) => {
            const captured = e.target.files?.[0]
            if (captured) handleFile(captured, true)
            e.target.value = ''
          }}
        />
      )}
    </div>
  )
}
