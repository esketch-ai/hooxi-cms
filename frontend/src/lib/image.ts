// 이미지 클라이언트 압축 유틸 — 태블릿 현장 사진 업로드용 (외부 라이브러리 금지)
// 실패(HEIC 등 디코딩 불가) 시 원본을 그대로 반환해 업로드 자체는 항상 성공시킨다.

/** 이미 충분히 작은 파일은 압축 생략하는 기준 (~500KB) */
const SKIP_SIZE_BYTES = 500 * 1024

/** File → 디코딩된 비트맵. createImageBitmap 우선, 미지원 시 Image+objectURL 폴백 */
async function decodeImage(file: File): Promise<ImageBitmap | HTMLImageElement> {
  if (typeof createImageBitmap === 'function') {
    try {
      // EXIF 방향 반영 명시 — 일부 브라우저는 기본값이 EXIF 무시라 세로 사진이 눕는다
      return await createImageBitmap(file, { imageOrientation: 'from-image' })
    } catch {
      // 폴백으로 진행 (일부 브라우저는 특정 포맷의 createImageBitmap 미지원)
    }
  }
  const url = URL.createObjectURL(file)
  try {
    return await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image()
      img.onload = () => resolve(img)
      img.onerror = () => reject(new Error('이미지 디코딩 실패'))
      img.src = url
    })
  } finally {
    URL.revokeObjectURL(url)
  }
}

/** canvas.toBlob Promise 래퍼 — 실패 시 null */
function canvasToBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))
}

/** 원본 파일명의 확장자를 .jpg로 교체 (확장자 없으면 그대로 유지) */
function toJpgName(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot > 0 ? `${name.slice(0, dot)}.jpg` : name
}

/**
 * 이미지 파일을 리사이즈·JPEG 압축한 새 File로 반환.
 * - 기본: 긴 변 1920px, 품질 0.8
 * - 이미지가 아니거나 이미 충분히 작으면(양 변 ≤ maxEdge, 크기 ≤ ~500KB) 원본 반환
 * - 디코딩/변환 실패 시 예외를 삼키고 원본 반환 (업로드는 항상 성공해야 함)
 */
export async function compressImage(
  file: File,
  opts?: { maxEdge?: number; quality?: number },
): Promise<File> {
  const maxEdge = opts?.maxEdge ?? 1920
  const quality = opts?.quality ?? 0.8

  if (!file.type.startsWith('image/')) return file

  try {
    const source = await decodeImage(file)
    const { width, height } = source
    try {
      // 이미 충분히 작으면 재인코딩하지 않는다 (화질 손실 방지)
      if (width <= maxEdge && height <= maxEdge && file.size <= SKIP_SIZE_BYTES) return file

      const scale = Math.min(1, maxEdge / Math.max(width, height))
      const w = Math.max(1, Math.round(width * scale))
      const h = Math.max(1, Math.round(height * scale))

      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      const ctx = canvas.getContext('2d')
      if (!ctx) return file
      ctx.drawImage(source, 0, 0, w, h)

      const blob = await canvasToBlob(canvas, quality)
      if (!blob) return file
      return new File([blob], toJpgName(file.name), { type: 'image/jpeg' })
    } finally {
      if ('close' in source) source.close()
    }
  } catch {
    return file
  }
}
