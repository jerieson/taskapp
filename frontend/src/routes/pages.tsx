import { lazy, Suspense, type ReactNode } from 'react'

import { FullPageSpinner } from '../components/Skeleton'

// Each screen is its own chunk. Inside the app shell, AppLayout's Suspense boundary
// shows a page skeleton while a chunk loads; public pages show the full-page loader.
export const AdminPage = lazy(() => import('../features/admin/AdminPage'))
export const InvitePage = lazy(() => import('../features/auth/InvitePage'))
export const LoginPage = lazy(() => import('../features/auth/LoginPage'))
export const ProfilePage = lazy(() => import('../features/auth/ProfilePage'))
export const ResetPasswordPage = lazy(() => import('../features/auth/ResetPasswordPage'))

export function PublicPage({ children }: { children: ReactNode }) {
  return <Suspense fallback={<FullPageSpinner />}>{children}</Suspense>
}
