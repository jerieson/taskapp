import type { Role } from '../api/auth'
import type { RunStatus } from '../api/processes'

export const ROLE_LABEL: Record<Role, string> = {
  admin: 'Admin',
  manager: 'Manager',
  dev: 'Developer',
}

export const RUN_STATUS_LABEL: Record<RunStatus, string> = {
  in_progress: 'In progress',
  completed: 'Completed',
  cancelled: 'Cancelled',
}

/** daisyUI badge classes (background + matching content color). */
export const RUN_STATUS_BADGE: Record<RunStatus, string> = {
  in_progress: 'badge-info',
  completed: 'badge-success',
  cancelled: 'badge-neutral',
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
