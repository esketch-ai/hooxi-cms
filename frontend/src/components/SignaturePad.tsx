import { useEffect, useRef, useState } from 'react'
import { CircleNotch, Eraser } from '@phosphor-icons/react'

interface SignaturePadProps {
  /** PNG Blob 저장 콜백 (흰 배경 + 검정 획 — 밝은 배경에서도 판독 가능) */
  onSave: (blob: Blob) => void | Promise<void>
  onCancel?: () => void
  disabled?: boolean
  saveLabel?: string
  cancelLabel?: string
  /** 서명 영역 높이(px) */
  height?: number
}

/** 획 두께(px, CSS 픽셀 기준) */
const STROKE_WIDTH = 2.5

/**
 * 태블릿 현장 서명 패드 — canvas + Pointer Events 직접 구현.
 * 터치·애플펜슬·마우스 대응(touch-action: none), devicePixelRatio 반영.
 */
export function SignaturePad({
  onSave,
  onCancel,
  disabled = false,
  saveLabel = '저장',
  cancelLabel = '취소',
  height = 220,
}: SignaturePadProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const drawingRef = useRef(false)
  const [hasStroke, setHasStroke] = useState(false)
  const [saving, setSaving] = useState(false)

  /** 흰 배경으로 초기화(지우기 겸용) */
  const fillBackground = (canvas: HTMLCanvasElement) => {
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.save()
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.restore()
  }

  // 마운트 시 1회 측정 — 리사이즈에 따른 서명 유실 방지를 위해 이후 크기 고정
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    const width = canvas.clientWidth
    canvas.width = Math.max(1, Math.round(width * dpr))
    canvas.height = Math.max(1, Math.round(height * dpr))
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.scale(dpr, dpr)
    ctx.lineWidth = STROKE_WIDTH
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.strokeStyle = '#000000'
    fillBackground(canvas)
  }, [height])

  const pointerPos = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = e.currentTarget
    const rect = canvas.getBoundingClientRect()
    // 비트맵 크기는 마운트 시 고정 — 회전 등으로 표시 크기가 바뀌어도 좌표계 보정
    const dpr = window.devicePixelRatio || 1
    const scaleX = canvas.width / dpr / rect.width
    const scaleY = canvas.height / dpr / rect.height
    return { x: (e.clientX - rect.left) * scaleX, y: (e.clientY - rect.top) * scaleY }
  }

  const handlePointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (disabled || saving) return
    const ctx = e.currentTarget.getContext('2d')
    if (!ctx) return
    e.currentTarget.setPointerCapture(e.pointerId)
    drawingRef.current = true
    const { x, y } = pointerPos(e)
    ctx.beginPath()
    ctx.moveTo(x, y)
    // 점 하나만 찍어도 획으로 인식되도록 제자리 선분
    ctx.lineTo(x, y)
    ctx.stroke()
    setHasStroke(true)
  }

  const handlePointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawingRef.current) return
    const ctx = e.currentTarget.getContext('2d')
    if (!ctx) return
    const { x, y } = pointerPos(e)
    ctx.lineTo(x, y)
    ctx.stroke()
  }

  const handlePointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawingRef.current) return
    drawingRef.current = false
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId)
    }
  }

  const handleClear = () => {
    const canvas = canvasRef.current
    if (!canvas) return
    fillBackground(canvas)
    setHasStroke(false)
  }

  const handleSave = () => {
    const canvas = canvasRef.current
    if (!canvas || !hasStroke || saving) return
    setSaving(true)
    canvas.toBlob(async (blob) => {
      try {
        if (blob) await onSave(blob)
      } finally {
        setSaving(false)
      }
    }, 'image/png')
  }

  return (
    <div className="flex flex-col gap-3">
      <div
        className={`overflow-hidden rounded-xl border border-hairline bg-white ${
          disabled ? 'opacity-60' : ''
        }`}
      >
        <canvas
          ref={canvasRef}
          className="block w-full touch-none"
          style={{ height }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          aria-label="서명 영역"
        />
      </div>
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={handleClear}
          disabled={disabled || saving || !hasStroke}
          className="flex items-center gap-1.5 rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate disabled:opacity-60"
        >
          <Eraser size={14} />
          지우기
        </button>
        <div className="flex gap-2">
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              disabled={saving}
              className="rounded-full border border-hairline px-4 py-2 text-sm font-medium text-bone hover:bg-elevate disabled:opacity-60"
            >
              {cancelLabel}
            </button>
          )}
          <button
            type="button"
            onClick={handleSave}
            disabled={disabled || saving || !hasStroke}
            className="flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-60"
          >
            {saving && <CircleNotch size={14} className="animate-spin" />}
            {saveLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
