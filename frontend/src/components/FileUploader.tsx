// 파일 업로더 (플랜 §4.2) — 드래그앤드롭 + 클릭 선택, SCR-12·13 공용
import { useRef, useState, type DragEvent } from 'react'
import { CloudArrowUp, FileText, X } from '@phosphor-icons/react'

interface FileUploaderProps {
  /** 선택 파일 (제어형) */
  file: File | null
  onChange: (file: File | null) => void
  accept?: string
  disabled?: boolean
  className?: string
}

export function FileUploader({
  file,
  onChange,
  accept,
  disabled = false,
  className = '',
}: FileUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragOver(false)
    if (disabled) return
    const dropped = e.dataTransfer.files?.[0]
    if (dropped) onChange(dropped)
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
      onKeyDown={(e) => e.key === 'Enter' && !disabled && inputRef.current?.click()}
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
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        disabled={disabled}
        className="hidden"
        onChange={(e) => {
          const selected = e.target.files?.[0]
          if (selected) onChange(selected)
          e.target.value = ''
        }}
      />
    </div>
  )
}
