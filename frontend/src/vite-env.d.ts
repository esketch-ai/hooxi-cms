/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Google Maps JS API 키 (SCR-09) — 프론트 공개분, §10.4 */
  readonly VITE_GOOGLE_MAPS_KEY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
