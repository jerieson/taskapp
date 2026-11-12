import type { Role } from '../../api/auth'
import { ROLE_LABEL } from '../../lib/labels'

const ROLE_BADGE: Record<Role, string> = {
  admin: 'badge-primary',
  manager: 'badge-secondary',
  dev: 'badge-accent',
}

export default function RoleBadge({ role }: { role: Role }) {
  return <span className={`badge badge-sm ${ROLE_BADGE[role]}`}>{ROLE_LABEL[role]}</span>
}
