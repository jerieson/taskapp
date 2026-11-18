/*
 * Weekly planning pieces shared by /today, /logs and the team dashboard: the deadline
 * countdown and the Friday reminder banner.
 */
import { Link } from 'react-router'

import { usePlanningStatus } from '../../api/planning'
import { AlertIcon, ClockIcon, LockIcon } from '../../components/icons'
import { formatDeadline, formatTimeLeft } from '../../lib/format'
import { useNow } from './planning'

/** "Due Fri, Nov 20, 6:30 PM · 2 d 4 h left", or "Locked" after the deadline. */
export function DeadlineCountdown({ week }: { week: { is_open: boolean; deadline: string } }) {
  const now = useNow()
  const left = Date.parse(week.deadline) - now
  if (!week.is_open || left <= 0) {
    return (
      <span className="flex flex-wrap items-center gap-2 text-sm">
        <span className="badge badge-neutral gap-1">
          <LockIcon className="size-3.5" />
          Locked
        </span>
        <span className="text-base-content/80">
          Planning closed {formatDeadline(week.deadline)}
        </span>
      </span>
    )
  }
  return (
    <span className="flex flex-wrap items-center gap-2 text-sm">
      <span className="badge badge-secondary gap-1">
        <ClockIcon className="size-3.5" />
        {formatTimeLeft(left)} left
      </span>
      <span className="text-base-content/80">Due {formatDeadline(week.deadline)}</span>
    </span>
  )
}

/** Shown on the Friday before next week until the deadline, while nothing is planned. */
export function PlanReminder({ className = '' }: { className?: string }) {
  const status = usePlanningStatus()
  if (!status.data?.show_reminder) return null
  return (
    <div role="alert" className={`alert alert-warning ${className}`}>
      <AlertIcon className="size-5" />
      <span>
        <strong>Next week isn’t planned yet.</strong> The plan is due{' '}
        {formatDeadline(status.data.deadline)}.
      </span>
      <Link to="/today?tab=plan" className="btn btn-sm">
        Plan next week
      </Link>
    </div>
  )
}
