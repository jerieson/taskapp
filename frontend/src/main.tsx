import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router/dom'

import { authKeys } from './api/auth'
import { setUnauthorizedHandler } from './api/client'
import { queryClient } from './api/queryClient'
import ToastProvider from './components/ToastProvider'
import './index.css'
import './lib/theme'
import { PUBLIC_PATH_PREFIXES, router } from './routes'

// A 401 on an API call means the session ended (expired, revoked or the user was
// deactivated): forget all cached data and go to /login, returning here afterwards.
setUnauthorizedHandler(() => {
  queryClient.removeQueries()
  queryClient.setQueryData(authKeys.me, null)
  const { pathname, search } = window.location
  if (PUBLIC_PATH_PREFIXES.some((prefix) => pathname.startsWith(prefix))) return
  void router.navigate(`/login?next=${encodeURIComponent(pathname + search)}`, { replace: true })
})

const root = document.getElementById('root')
if (!root) throw new Error('Root element #root not found')

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
)
