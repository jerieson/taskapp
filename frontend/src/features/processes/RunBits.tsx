import type { Run, RunStatus } from '../../api/processes'
import { RUN_STATUS_BADGE, RUN_STATUS_LABEL } from '../../lib/labels'

export function RunStatusBadge({ status }: { status: RunStatus }) {
  return (
    <span className={`badge badge-sm ${RUN_STATUS_BADGE[status]}`}>{RUN_STATUS_LABEL[status]}</span>
  )
}

/** Done / total tasks as a bar plus a text count. */
export function RunProgressBar({
  run,
  label,
}: {
  run: Pick<Run, 'progress' | 'status'>
  label: string
}) {
  const { done, total } = run.progress
  const complete = total > 0 && done === total
  return (
    <div className="flex items-center gap-3">
      <progress
        className={`progress h-2.5 flex-1 ${complete ? 'progress-success' : 'progress-primary'}`}
        value={done}
        max={Math.max(total, 1)}
        aria-label={label}
        aria-valuetext={`${done} of ${total} tasks done`}
      />
      <span className="shrink-0 text-sm text-base-content/80 tabular-nums">
        {done} / {total}
      </span>
    </div>
  )
}
