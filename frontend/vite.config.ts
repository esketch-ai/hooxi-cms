import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // 절대 경로 필수 — './'는 중첩 라우트(/clients/:id) 직접 접속 시 자산 경로가
  // /clients/assets/…로 해석돼 SPA 폴백(HTML)을 받아 백지가 된다
  base: '/',
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
