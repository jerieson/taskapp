import { lazy, Suspense, type ReactNode } from 'react'

import { FullPageSpinner } from '../components/Skeleton'

// Each screen is its own chunk. Inside the app shell, AppLayout's Suspense boundary
// shows a page skeleton while a chunk loads; public pages show the full-page loader.
export const AdminPage = lazy(() => import('../features/admin/AdminPage'))
export const DashboardPage = lazy(() => import('../features/dashboard/DashboardPage'))
export const InvitePage = lazy(() => import('../features/auth/InvitePage'))
export const LogsPage = lazy(() => import('../features/logs/LogsPage'))
export const LoginPage = lazy(() => import('../features/auth/LoginPage'))
export const ProcessesPage = lazy(() => import('../features/processes/ProcessesPage'))
export const ProcessPage = lazy(() => import('../features/processes/ProcessPage'))
export const ProfilePage = lazy(() => import('../features/auth/ProfilePage'))
export const ResetPasswordPage = lazy(() => import('../features/auth/ResetPasswordPage'))
export const RunPage = lazy(() => import('../features/processes/RunPage'))
export const TasksPage = lazy(() => import('../features/tasks/TasksPage'))
export const TodayPage = lazy(() => import('../features/daily-plan/TodayPage'))
export const TeamLogsPage = lazy(() => import('../features/logs/TeamLogsPage'))

export function PublicPage({ children }: { children: ReactNode }) {
  return <Suspense fallback={<FullPageSpinner />}>{children}</Suspense>
}
