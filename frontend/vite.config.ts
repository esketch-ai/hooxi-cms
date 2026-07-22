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
    // 단일 번들(1MB+) 분리 — 벤더를 별도 청크로. rolldown(vite v8)은 함수형 manualChunks 사용.
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('@phosphor-icons')) return 'icons'
          if (id.includes('@tanstack') || id.includes('/axios/')) return 'query'
          if (
            id.includes('/react-dom/') ||
            id.includes('/react-router') ||
            id.includes('/react/')
          )
            return 'react-vendor'
          return 'vendor'
        },
      },
    },
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
