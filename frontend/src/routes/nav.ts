import type { ComponentType, SVGProps } from 'react'

import type { Role } from '../api/auth'
import {
  CalendarIcon,
  ChartIcon,
  CheckSquareIcon,
  ClockIcon,
  RepeatIcon,
  ShieldIcon,
  UsersIcon,
} from '../components/icons'

export interface NavItem {
  to: string
  label: string
  icon: ComponentType<SVGProps<SVGSVGElement>>
}

export interface NavSection {
  title: string
  items: NavItem[]
  /** Roles that see this section. Must match the route guards in routes/index.tsx. */
  roles: readonly Role[]
}

export const TEAM_ROLES = ['manager', 'admin'] as const satisfies readonly Role[]
export const ADMIN_ROLES = ['admin'] as const satisfies readonly Role[]

export const NAV_SECTIONS: NavSection[] = [
  {
    title: 'My work',
    roles: ['admin', 'manager', 'dev'],
    items: [
      { to: '/today', label: 'Today', icon: CalendarIcon },
      { to: '/tasks', label: 'Tasks', icon: CheckSquareIcon },
      { to: '/logs', label: 'Logs', icon: ClockIcon },
      { to: '/processes', label: 'Processes', icon: RepeatIcon },
      { to: '/dashboard', label: 'Dashboard', icon: ChartIcon },
    ],
  },
  {
    title: 'Team',
    roles: TEAM_ROLES,
    items: [
      { to: '/team/logs', label: 'Team logs', icon: ClockIcon },
      { to: '/team/dashboard', label: 'Team dashboard', icon: UsersIcon },
    ],
  },
  {
    title: 'Admin',
    roles: ADMIN_ROLES,
    items: [{ to: '/admin', label: 'Admin', icon: ShieldIcon }],
  },
]
