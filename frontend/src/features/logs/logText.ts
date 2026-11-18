/* Short text descriptions of a prod log row (toasts, confirmations). */
import type { ProdLog } from '../../api/logs'
import { formatHours } from '../../lib/format'

/** One line naming a log, e.g. for toasts and delete confirmations. */
export function logLabel(log: ProdLog): string {
  return log.title ? `${log.activity.label}: ${log.title}` : log.activity.label
}

/** "2 h", "2 h of 3 h planned" or "3 h planned". */
export function logHours(log: ProdLog): string {
  if (log.hours_spent === null) return `${formatHours(log.planned_hours ?? 0)} planned`
  if (log.planned_hours === null) return formatHours(log.hours_spent)
  return `${formatHours(log.hours_spent)} of ${formatHours(log.planned_hours)} planned`
}
