import { createBrowserRouter, Navigate } from 'react-router'

import PlaceholderPage from '../components/PlaceholderPage'
import AdminPage from '../features/admin/AdminPage'
import InvitePage from '../features/auth/InvitePage'
import LoginPage from '../features/auth/LoginPage'
import ProfilePage from '../features/auth/ProfilePage'
import ResetPasswordPage from '../features/auth/ResetPasswordPage'
import AppLayout from '../layouts/AppLayout'
import { RedirectIfAuthenticated, RequireAuth, RequireRole } from './guards'
import { ADMIN_ROLES, TEAM_ROLES } from './nav'
import NotFoundPage from './NotFoundPage'
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
            <LoginPage />
          </RedirectIfAuthenticated>
        ),
      },
      { path: '/invite/:token', element: <InvitePage /> },
      { path: '/reset-password/:token', element: <ResetPasswordPage /> },
      {
        element: <RequireAuth />,
        children: [
          {
            element: <AppLayout />,
            children: [
              { index: true, element: <Navigate to="/today" replace /> },
              { path: 'today', element: <PlaceholderPage title="Today" /> },
              { path: 'tasks', element: <PlaceholderPage title="Tasks" /> },
              { path: 'logs', element: <PlaceholderPage title="Logs" /> },
              { path: 'processes', element: <PlaceholderPage title="Processes" /> },
              { path: 'processes/:id', element: <PlaceholderPage title="Process" /> },
              { path: 'runs/:id', element: <PlaceholderPage title="Process run" /> },
              { path: 'dashboard', element: <PlaceholderPage title="Dashboard" /> },
              { path: 'profile', element: <ProfilePage /> },
              {
                path: 'team/logs',
                element: (
                  <RequireRole roles={TEAM_ROLES}>
                    <PlaceholderPage title="Team logs" />
                  </RequireRole>
                ),
              },
              {
                path: 'team/dashboard',
                element: (
                  <RequireRole roles={TEAM_ROLES}>
                    <PlaceholderPage title="Team dashboard" />
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
