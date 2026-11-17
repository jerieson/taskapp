/*
 * Searchable list of the user's open tasks that are not in the plan yet. Adding keeps
 * the picker open so several tasks can be added in a row.
 */
import { useState } from 'react'
import { Link } from 'react-router'

import { errorMessage } from '../../api/client'
import { useAddPlanItem, type Plan } from '../../api/plans'
import { useTaskOptions, type Task } from '../../api/tasks'
import AsyncState from '../../components/AsyncState'
import EmptyState from '../../components/EmptyState'
import { CheckSquareIcon, PlusIcon } from '../../components/icons'
import { SkeletonText } from '../../components/Skeleton'
import { useToast } from '../../components/toast-context'
import { formatDay } from '../../lib/format'

interface TaskPickerProps {
  planDate: string
  /** null when the date has no plan yet (adding the first task creates it). */
  plan: Plan | null
  onDone: () => void
}

export default function TaskPicker({ planDate, plan, onDone }: TaskPickerProps) {
  const toast = useToast()
  const tasks = useTaskOptions()
  const add = useAddPlanItem(planDate)
  const [search, setSearch] = useState('')
  const [addingId, setAddingId] = useState<number | null>(null)

  const planned = new Set(plan?.items.map((item) => item.task.id))
  const available = (tasks.data ?? []).filter((task) => !planned.has(task.id))
  const query = search.trim().toLowerCase()
  const matches = query
    ? available.filter((task) => task.title.toLowerCase().includes(query))
    : available

  function addTask(task: Task) {
    setAddingId(task.id)
    add.mutate(
      { planId: plan?.id ?? null, task_id: task.id },
      {
        onSuccess: () => toast.success(`Added “${task.title}”`),
        onError: (error) => toast.error(errorMessage(error)),
        onSettled: () => setAddingId(null),
      },
    )
  }

  return (
    <div>
      <label className="input mt-2 w-full">
        <span className="sr-only">Search open tasks</span>
        <input
          type="search"
          placeholder="Search open tasks"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          autoComplete="off"
        />
      </label>

      <div className="mt-3 max-h-[50vh] overflow-y-auto">
        <AsyncState
          query={tasks}
          isEmpty={matches.length === 0}
          skeleton={<SkeletonText lines={4} />}
          empty={
            <EmptyState
              size="compact"
              icon={<CheckSquareIcon className="size-6" />}
              title={
                query
                  ? 'No open tasks match'
                  : available.length === 0 && planned.size > 0
                    ? 'All your open tasks are planned'
                    : 'No open tasks'
              }
              action={
                query ? undefined : (
                  <Link to="/tasks" className="btn">
                    Go to tasks
                  </Link>
                )
              }
            />
          }
        >
          {() => (
            <ul className="flex flex-col divide-y divide-base-300" aria-label="Open tasks">
              {matches.map((task) => (
                <li key={task.id} className="flex items-center gap-3 py-2">
                  <div className="flex min-w-0 flex-1 flex-col">
                    <span className="break-words">{task.title}</span>
                    <span className="flex flex-wrap items-center gap-2 text-xs text-base-content/80">
                      <span>{task.priority.label}</span>
                      {task.due_date && <span>Due {formatDay(task.due_date)}</span>}
                      {task.is_overdue && (
                        <span className="badge badge-sm badge-error">Overdue</span>
                      )}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => addTask(task)}
                    disabled={add.isPending}
                    aria-label={`Add “${task.title}”`}
                  >
                    {addingId === task.id ? (
                      <span className="loading loading-spinner loading-xs" />
                    ) : (
                      <PlusIcon className="size-4" />
                    )}
                    Add
                  </button>
                </li>
              ))}
            </ul>
          )}
        </AsyncState>
      </div>

      <div className="modal-action">
        <button type="button" className="btn btn-primary" onClick={onDone}>
          Done
        </button>
      </div>
    </div>
  )
}
