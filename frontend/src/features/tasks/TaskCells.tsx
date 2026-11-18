/*
 * Task list cells shared by /tasks and /runs/:id.
 */

import { errorMessage } from '../../api/client'
import { useSelectOptions } from '../../api/lookups'
import { useUpdateTask, type Task } from '../../api/tasks'
import ColorDot from '../../components/ColorDot'
import { useToast } from '../../components/toast-context'
import { formatDay } from '../../lib/format'

export function StatusQuickSelect({ task }: { task: Task }) {
  const toast = useToast()
  const update = useUpdateTask()
  const { options, isPending } = useSelectOptions('statuses', task.status)

  function change(statusId: number) {
    update.mutate(
      { id: task.id, status_id: statusId },
      {
        onSuccess: (saved) => toast.success(`“${saved.title}” is now ${saved.status.label}`),
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  return (
    <span className="inline-flex items-center gap-2">
      <ColorDot color={task.status.color} />
      <select
        className="select select-sm w-40 max-w-full"
        aria-label={`Status of ${task.title}`}
        value={task.status.id}
        disabled={isPending || update.isPending}
        onChange={(event) => change(Number(event.target.value))}
      >
        {isPending ? (
          <option value={task.status.id}>{task.status.label}</option>
        ) : (
          options.map((option) => (
            <option key={option.id} value={option.id}>
              {option.isActive ? option.label : `${option.label} (inactive)`}
            </option>
          ))
        )}
      </select>
    </span>
  )
}

/** Title with project/category. */
export function TaskTitle({ task }: { task: Task }) {
  const meta = [task.project?.name, task.category?.label].filter(Boolean)
  return (
    <span className="flex min-w-0 flex-col gap-0.5">
      <span className={`break-words ${task.status.is_done ? 'line-through opacity-80' : ''}`}>
        {task.title}
      </span>
      {meta.length > 0 && (
        <span className="text-xs font-normal break-words text-base-content/80">
          {meta.join(' · ')}
        </span>
      )}
    </span>
  )
}

export function DueCell({ task }: { task: Task }) {
  if (!task.due_date) return <span className="text-base-content/80">—</span>
  return (
    <span className="inline-flex flex-wrap items-center justify-end gap-2 md:justify-start">
      <span>{formatDay(task.due_date)}</span>
      {task.is_overdue && <span className="badge badge-sm badge-error">Overdue</span>}
    </span>
  )
}
