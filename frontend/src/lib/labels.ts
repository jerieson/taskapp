import type { Role } from '../api/auth'

export const ROLE_LABEL: Record<Role, string> = {
  admin: 'Admin',
  manager: 'Manager',
  dev: 'Developer',
}

/** "former member" / "deactivated" for someone listed on a team view, or undefined. */
export function memberNote(member: {
  is_current_member: boolean
  is_active: boolean
}): string | undefined {
  const notes = [
    !member.is_current_member && 'former member',
    !member.is_active && 'deactivated',
  ].filter(Boolean)
  return notes.length ? notes.join(', ') : undefined
}
