/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Google Maps JS API 키 (SCR-09) — 프론트 공개분, §10.4 */
  readonly VITE_GOOGLE_MAPS_KEY?: string
  /** Naver Maps JS API v3 Client ID (SCR-09) — NCP Maps Application, 도메인 등록 필요 */
  readonly VITE_NAVER_MAPS_CLIENT_ID?: string
  /** Kakao Maps JS SDK JavaScript 키 (SCR-09) — 카카오 개발자 앱, 플랫폼 Web 도메인 등록 필요 */
  readonly VITE_KAKAO_MAPS_JS_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
