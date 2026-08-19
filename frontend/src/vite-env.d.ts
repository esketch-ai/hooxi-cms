/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Google Maps JS API 키 (SCR-09) — 프론트 공개분, §10.4 */
  readonly VITE_GOOGLE_MAPS_KEY?: string
  /** Kakao Maps JS SDK JavaScript 키 (SCR-09) — 카카오 개발자 앱, 플랫폼 Web 도메인 등록 필요 */
  readonly VITE_KAKAO_MAPS_JS_KEY?: string
  /** 재무·정산·자산관리 기능군 은닉 플래그 — 'off' 일 때만 은닉, 그 외/미설정은 전체 노출 */
  readonly VITE_FEATURE_FINANCE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
