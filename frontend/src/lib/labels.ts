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
