import type { Role } from '../api/auth'

export const ROLE_LABEL: Record<Role, string> = {
  admin: 'Admin',
  manager: 'Manager',
  dev: 'Developer',
}
