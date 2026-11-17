import type { ReactNode } from 'react'

import type { TaskCounts } from '../../api/dashboard'
import { AlertIcon, CheckCircleIcon, ListIcon } from '../../components/icons'

function Stat({
  label,
  value,
  hint,
  icon,
  badge,
}: {
  label: string
  value: number
  hint: string
  icon: ReactNode
  badge?: ReactNode
}) {
  return (
    <div className="card card-border border-base-300 bg-base-100">
      <div className="card-body flex-row items-start gap-3 p-4">
        <span className="rounded-field bg-base-200 p-2 text-base-content" aria-hidden="true">
          {icon}
        </span>
        <div className="min-w-0">
          <p className="text-sm text-base-content/80">{label}</p>
          <p className="text-3xl font-bold tabular-nums">{value}</p>
          <p className="text-xs text-base-content/80">{hint}</p>
          {badge}
        </div>
      </div>
    </div>
  )
}

export default function TaskStats({ counts }: { counts: TaskCounts }) {
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <Stat
        label="Completed"
        value={counts.completed}
        hint="Tasks finished in this range"
        icon={<CheckCircleIcon />}
      />
      <Stat label="Open" value={counts.open} hint="Not done yet, right now" icon={<ListIcon />} />
      <Stat
        label="Overdue"
        value={counts.overdue}
        hint="Open and past their due date"
        icon={<AlertIcon />}
        badge={
          counts.overdue > 0 && (
            <span className="badge badge-sm mt-2 bg-warning text-warning-content border-warning">
              Needs attention
            </span>
          )
        }
      />
    </div>
  )
}
