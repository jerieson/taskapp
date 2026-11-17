import type { Plan } from '../../api/plans'
import { formatHours } from '../../lib/format'

/** Planned hours against WORKDAY_HOURS, plus how many tasks are done. */
export default function PlanSummary({ plan }: { plan: Plan }) {
  const { total_hours: total, workday_hours: workday } = plan
  const over = total - workday
  const done = plan.items.filter((item) => item.task.status.is_done).length
  const unestimated = plan.items.filter((item) => item.suggested_hours === null).length

  return (
    <section
      className="card card-border mb-4 border-base-300 bg-base-100"
      aria-label="Plan summary"
    >
      <div className="card-body gap-3 p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <p>
            <span className="text-2xl font-bold">{formatHours(total)}</span>{' '}
            <span className="text-base-content/80">planned of {formatHours(workday)}</span>
          </p>
          <p className="text-sm text-base-content/80">
            {done} of {plan.items.length} {plan.items.length === 1 ? 'task' : 'tasks'} done
          </p>
        </div>
        <progress
          className={`progress w-full ${over > 0 ? 'progress-warning' : 'progress-primary'}`}
          value={Math.min(total, workday)}
          max={workday}
          aria-label="Planned hours of the workday"
        />
        {(over > 0 || unestimated > 0) && (
          <div className="flex flex-wrap gap-2">
            {over > 0 && (
              <span className="badge badge-warning">{formatHours(over)} over the workday</span>
            )}
            {unestimated > 0 && (
              <span className="badge badge-ghost">{unestimated} without hours</span>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
