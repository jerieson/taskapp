import { createBrowserRouter, Navigate } from 'react-router'

import AppLayout from '../layouts/AppLayout'
import { RedirectIfAuthenticated, RequireAuth, RequireRole } from './guards'
import { ADMIN_ROLES, TEAM_ROLES } from './nav'
import NotFoundPage from './NotFoundPage'
import {
  AdminPage,
  DashboardPage,
  InvitePage,
  LoginPage,
  LogsPage,
  ProfilePage,
  PublicPage,
  ResetPasswordPage,
  SupportEntryPage,
  SupportPage,
  TasksPage,
  TeamDashboardPage,
  TeamLogsPage,
  TodayPage,
} from './pages'
import RouteErrorPage from './RouteErrorPage'

/** Paths that work without a session (no redirect to /login on 401). */
export const PUBLIC_PATH_PREFIXES = ['/login', '/invite/', '/reset-password/'] as const

export const router = createBrowserRouter([
  {
    errorElement: <RouteErrorPage />,
    children: [
      {
        path: '/login',
        element: (
          <RedirectIfAuthenticated>
            <PublicPage>
              <LoginPage />
            </PublicPage>
          </RedirectIfAuthenticated>
        ),
      },
      {
        path: '/invite/:token',
        element: (
          <PublicPage>
            <InvitePage />
          </PublicPage>
        ),
      },
      {
        path: '/reset-password/:token',
        element: (
          <PublicPage>
            <ResetPasswordPage />
          </PublicPage>
        ),
      },
      {
        element: <RequireAuth />,
        children: [
          {
            element: <AppLayout />,
            children: [
              { index: true, element: <Navigate to="/today" replace /> },
              { path: 'today', element: <TodayPage /> },
              { path: 'tasks', element: <TasksPage /> },
              { path: 'logs', element: <LogsPage /> },
              { path: 'support', element: <SupportPage /> },
              { path: 'support/:id', element: <SupportEntryPage /> },
              { path: 'dashboard', element: <DashboardPage /> },
              { path: 'profile', element: <ProfilePage /> },
              {
                path: 'team/logs',
                element: (
                  <RequireRole roles={TEAM_ROLES}>
                    <TeamLogsPage />
                  </RequireRole>
                ),
              },
              {
                path: 'team/dashboard',
                element: (
                  <RequireRole roles={TEAM_ROLES}>
                    <TeamDashboardPage />
                  </RequireRole>
                ),
              },
              {
                path: 'admin',
                element: (
                  <RequireRole roles={ADMIN_ROLES}>
                    <AdminPage />
                  </RequireRole>
                ),
              },
              { path: '*', element: <NotFoundPage /> },
            ],
          },
        ],
      },
    ],
  },
])
