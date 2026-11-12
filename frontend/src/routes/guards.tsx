import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router'

import { useCurrentUser, type Role } from '../api/auth'
import ErrorAlert from '../components/ErrorAlert'
import { FullPageSpinner } from '../components/Skeleton'
import NotFoundPage from './NotFoundPage'

/** Renders child routes only for a logged-in user; otherwise redirects to /login. */
export function RequireAuth() {
  const { data: user, isPending, error, refetch } = useCurrentUser()
  const location = useLocation()

  if (isPending) return <FullPageSpinner />
  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-base-100 p-4">
        <div className="w-full max-w-md">
          <ErrorAlert error={error} onRetry={() => void refetch()} />
        </div>
      </div>
    )
  }
  if (!user) {
    const next = `${location.pathname}${location.search}`
    const to = next === '/' ? '/login' : `/login?next=${encodeURIComponent(next)}`
    return <Navigate to={to} replace />
  }
  return <Outlet />
}

/**
 * Renders its children only for the given roles. Others see the not-found page,
 * matching the backend's 404 for resources a user may not see. UI only: the backend
 * enforces the real permission.
 */
export function RequireRole({ roles, children }: { roles: readonly Role[]; children: ReactNode }) {
  const { data: user } = useCurrentUser()
  if (!user || !roles.includes(user.role)) return <NotFoundPage />
  return <>{children}</>
}

/** For /login: a logged-in user goes straight to the app. */
export function RedirectIfAuthenticated({ children }: { children: ReactNode }) {
  const { data: user, isPending } = useCurrentUser()
  if (isPending) return <FullPageSpinner />
  if (user) return <Navigate to="/today" replace />
  return <>{children}</>
}
