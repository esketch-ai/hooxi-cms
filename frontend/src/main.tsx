import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import './index.css'
import { queryClient } from './app/queryClient'
import { ThemeProvider } from './app/ThemeProvider'
import { AuthProvider } from './app/AuthProvider'
import { PrivacyProvider } from './app/PrivacyProvider'
import { ToastProvider } from './components/Toast'
import { router } from './app/router'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <PrivacyProvider>
            <ToastProvider>
              <RouterProvider router={router} />
            </ToastProvider>
          </PrivacyProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
)
