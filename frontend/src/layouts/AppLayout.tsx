/*
 * Authenticated shell: daisyUI drawer with a sidebar that is permanent from lg up
 * and a slide-over (hamburger button) below lg, plus the top navbar.
 */
import { Fragment, useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router'

import { useCurrentUser, useLogout, type CurrentUser } from '../api/auth'
import Brand from '../components/Brand'
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  LogoutIcon,
  MenuIcon,
  UserIcon,
} from '../components/icons'
import ThemeToggle from '../components/ThemeToggle'
import { useToast } from '../components/toast-context'
import { NAV_SECTIONS } from '../routes/nav'

const DRAWER_ID = 'app-drawer'
const SIDEBAR_ID = 'app-sidebar'

const ROLE_LABEL: Record<CurrentUser['role'], string> = {
  admin: 'Admin',
  manager: 'Manager',
  dev: 'Developer',
}

function closeDropdown() {
  if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
}

function UserMenu({ user }: { user: CurrentUser }) {
  const logout = useLogout()
  const navigate = useNavigate()
  const toast = useToast()

  function handleLogout() {
    closeDropdown()
    logout.mutate(undefined, {
      onSuccess: () => void navigate('/login', { replace: true }),
      onError: () => {
        toast.error('Could not reach the server; you were logged out on this device only.')
        void navigate('/login', { replace: true })
      },
    })
  }

  return (
    <div className="dropdown dropdown-end">
      <div
        tabIndex={0}
        role="button"
        className="btn btn-ghost gap-2 px-2"
        aria-label={`Account menu for ${user.username}`}
      >
        <span className="avatar avatar-placeholder">
          <span className="w-8 rounded-full bg-primary text-primary-content">
            <span className="text-sm uppercase">{user.username.slice(0, 2)}</span>
          </span>
        </span>
        <span className="hidden max-w-32 truncate sm:inline">{user.username}</span>
      </div>
      <ul
        tabIndex={-1}
        className="menu dropdown-content z-30 mt-2 w-60 rounded-box border border-base-300 bg-base-100 p-2 shadow"
      >
        <li className="menu-title text-base-content/70">
          <span className="truncate text-base-content">{user.username}</span>
          <span className="font-normal">
            {ROLE_LABEL[user.role]}
            {user.team && ` · ${user.team.name}`}
          </span>
        </li>
        <li>
          <Link to="/profile" onClick={closeDropdown}>
            <UserIcon className="size-4" /> Profile
          </Link>
        </li>
        <li>
          <button type="button" onClick={handleLogout} disabled={logout.isPending}>
            <LogoutIcon className="size-4" /> Log out
          </button>
        </li>
      </ul>
    </div>
  )
}

const COLLAPSED_KEY = 'taskapp-sidebar-collapsed'

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === '1'
  } catch {
    return false
  }
}

function saveCollapsed(collapsed: boolean) {
  try {
    if (collapsed) localStorage.setItem(COLLAPSED_KEY, '1')
    else localStorage.removeItem(COLLAPSED_KEY)
  } catch {
    // Storage blocked: the choice lasts for this page only.
  }
}

interface SidebarProps {
  user: CurrentUser
  /** Icon-only rail. Applies from lg up; the mobile slide-over is always full width. */
  collapsed: boolean
  onToggleCollapsed: () => void
}

function Sidebar({ user, collapsed, onToggleCollapsed }: SidebarProps) {
  const sections = NAV_SECTIONS.filter((section) => section.roles.includes(user.role))
  // Classes that apply only while collapsed on large screens.
  const lgCollapsed = (classes: string) => (collapsed ? classes : '')

  return (
    <nav
      id={SIDEBAR_ID}
      className={`flex min-h-full w-64 flex-col bg-base-200 transition-[width] duration-200 ${lgCollapsed('lg:w-18')}`}
      aria-label="Main"
    >
      <div className={`flex h-16 items-center px-5 ${lgCollapsed('lg:justify-center lg:px-0')}`}>
        <Brand linked nameClassName={lgCollapsed('lg:sr-only')} />
      </div>

      <ul className="menu w-full flex-1 gap-1 px-3 pb-4">
        {sections.map((section, index) => (
          <Fragment key={section.title}>
            <li
              className={`menu-title mt-2 text-xs tracking-wide text-base-content/80 uppercase ${
                index === 0 ? 'mt-0' : ''
              } ${lgCollapsed('lg:sr-only')}`}
            >
              {section.title}
            </li>
            {collapsed && index > 0 && (
              <li aria-hidden="true" className="my-2 hidden h-px bg-base-300 lg:block" />
            )}
            {section.items.map(({ to, label, icon: Icon }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  title={collapsed ? label : undefined}
                  className={({ isActive }) =>
                    `gap-3 py-2.5 font-medium ${isActive ? 'menu-active' : ''} ${lgCollapsed('lg:justify-center lg:px-0')}`
                  }
                >
                  <Icon className="size-4 shrink-0" />
                  <span className={lgCollapsed('lg:sr-only')}>{label}</span>
                </NavLink>
              </li>
            ))}
          </Fragment>
        ))}
      </ul>

      <div className="hidden border-t border-base-300 p-3 lg:block">
        <button
          type="button"
          className={`btn btn-ghost btn-sm w-full font-medium ${collapsed ? 'justify-center px-0' : 'justify-start gap-3'}`}
          onClick={onToggleCollapsed}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!collapsed}
          title={collapsed ? 'Expand sidebar' : undefined}
        >
          {collapsed ? (
            <ChevronRightIcon className="size-4" />
          ) : (
            <>
              <ChevronLeftIcon className="size-4" />
              Collapse
            </>
          )}
        </button>
      </div>
    </nav>
  )
}

export default function AppLayout() {
  const { data: user } = useCurrentUser()
  const location = useLocation()
  // The slide-over is open only on the path it was opened from, so any navigation
  // closes it.
  const [openOnPath, setOpenOnPath] = useState<string | null>(null)
  const drawerOpen = openOnPath === location.pathname
  const setDrawerOpen = (open: boolean) => setOpenOnPath(open ? location.pathname : null)
  const [collapsed, setCollapsed] = useState(readCollapsed)

  function toggleCollapsed() {
    setCollapsed((current) => {
      saveCollapsed(!current)
      return !current
    })
  }

  // Escape closes the slide-over.
  useEffect(() => {
    if (!drawerOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpenOnPath(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [drawerOpen])

  // RequireAuth renders this layout only once the user is loaded.
  if (!user) return null

  return (
    <div className="drawer lg:drawer-open">
      <input
        id={DRAWER_ID}
        type="checkbox"
        className="drawer-toggle"
        checked={drawerOpen}
        onChange={(event) => setDrawerOpen(event.target.checked)}
        aria-hidden="true"
        tabIndex={-1}
      />
      <div className="drawer-content flex min-h-screen min-w-0 flex-col bg-base-100 text-base-content">
        <header className="navbar sticky top-0 z-20 gap-2 border-b border-base-300 bg-base-100 px-2 sm:px-4">
          <div className="navbar-start gap-1">
            <button
              type="button"
              className="btn btn-ghost btn-square lg:hidden"
              onClick={() => setDrawerOpen(true)}
              aria-label="Open navigation"
              aria-controls={SIDEBAR_ID}
              aria-expanded={drawerOpen}
            >
              <MenuIcon />
            </button>
            <div className="lg:hidden">
              <Brand linked />
            </div>
          </div>
          <div className="navbar-end gap-1">
            <ThemeToggle />
            <UserMenu user={user} />
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl min-w-0 flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
      <div className="drawer-side z-40">
        <label htmlFor={DRAWER_ID} aria-label="Close navigation" className="drawer-overlay" />
        <Sidebar user={user} collapsed={collapsed} onToggleCollapsed={toggleCollapsed} />
      </div>
    </div>
  )
}
