import { useState } from 'react'

import { errorMessage } from '../../api/client'
import { useLookups } from '../../api/lookups'
import { useUpdatePlanItem, type PlanItem } from '../../api/plans'
import { useUpdateTask } from '../../api/tasks'
import ColorDot from '../../components/ColorDot'
import { ArrowDownIcon, ArrowUpIcon, ClockIcon, TrashIcon } from '../../components/icons'
import { useToast } from '../../components/toast-context'
import { formatDay } from '../../lib/format'

const HOURS_PATTERN = /^\d{1,2}(\.\d{1,2})?$/

interface PlanItemCardProps {
  item: PlanItem
  planId: number
  planDate: string
  /** 1-based, for screen readers. */
  position: number
  isFirst: boolean
  isLast: boolean
  /** A reorder/remove of any item is in flight. */
  isBusy: boolean
  onMove: (by: -1 | 1) => void
  onRemove: () => void
  onLogWork: () => void
}

export default function PlanItemCard({
  item,
  planId,
  planDate,
  position,
  isFirst,
  isLast,
  isBusy,
  onMove,
  onRemove,
  onLogWork,
}: PlanItemCardProps) {
  const { task } = item
  const done = task.status.is_done
  const meta = [task.project?.name, task.category?.label].filter(Boolean)

  const removeButton = (className: string) => (
    <button
      type="button"
      className={`btn btn-sm btn-ghost btn-square shrink-0 ${className}`}
      onClick={onRemove}
      disabled={isBusy}
      aria-label={`Remove “${task.title}” from the plan`}
      title="Remove from plan"
    >
      <TrashIcon className="size-4" />
    </button>
  )

  return (
    <li className="card card-border border-base-300 bg-base-100">
      <div className="card-body flex-col gap-3 p-3 sm:p-4 md:flex-row md:items-center">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <DoneToggle item={item} />
          <div className="flex min-w-0 flex-1 flex-col gap-1 pt-0.5">
            <span className="sr-only">{position}.</span>
            <span className={`font-medium break-words ${done ? 'line-through opacity-80' : ''}`}>
              {task.title}
            </span>
            {meta.length > 0 && (
              <span className="text-xs break-words text-base-content/80">{meta.join(' · ')}</span>
            )}
            <span className="flex flex-wrap items-center gap-2 text-xs text-base-content/80">
              <span className="inline-flex items-center gap-1">
                <ColorDot color={task.priority.color} />
                {task.priority.label}
              </span>
              {task.due_date && <span>Due {formatDay(task.due_date)}</span>}
              {task.is_overdue && <span className="badge badge-sm badge-error">Overdue</span>}
              {done && <span className="badge badge-sm badge-success">Done</span>}
            </span>
          </div>
          {/* Below md the remove button sits beside the title so the controls fit one row. */}
          {removeButton('-mt-1 -mr-1 md:hidden')}
        </div>

        <div className="flex flex-wrap items-center gap-2 md:flex-nowrap">
          <HoursInput item={item} planId={planId} planDate={planDate} />
          <div className="join">
            <button
              type="button"
              className="btn join-item btn-sm btn-square"
              onClick={() => onMove(-1)}
              disabled={isFirst || isBusy}
              aria-label={`Move “${task.title}” up`}
            >
              <ArrowUpIcon className="size-4" />
            </button>
            <button
              type="button"
              className="btn join-item btn-sm btn-square"
              onClick={() => onMove(1)}
              disabled={isLast || isBusy}
              aria-label={`Move “${task.title}” down`}
            >
              <ArrowDownIcon className="size-4" />
            </button>
          </div>
          <button type="button" className="btn btn-sm" onClick={onLogWork}>
            <ClockIcon className="size-4" />
            Log work
          </button>
          {removeButton('hidden md:inline-flex')}
        </div>
      </div>
    </li>
  )
}

/**
 * Checked = the task's status counts as done. Checking moves it to the first done
 * status in the admin's order; unchecking moves it back to the default status.
 */
function DoneToggle({ item }: { item: PlanItem }) {
  const toast = useToast()
  const statuses = useLookups('statuses')
  const update = useUpdateTask()
  const { task } = item
  const done = task.status.is_done
  const target = done
    ? statuses.data?.find((s) => s.is_default)
    : statuses.data?.find((s) => s.is_done)

  function toggle() {
    if (!target) return
    update.mutate(
      { id: task.id, status_id: target.id },
      {
        onSuccess: (saved) =>
          toast.success(
            saved.status.is_done
              ? `“${saved.title}” done`
              : `“${saved.title}” is ${saved.status.label} again`,
          ),
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  return (
    <label className="flex size-11 shrink-0 cursor-pointer items-center justify-center -m-2.5">
      <input
        type="checkbox"
        className="checkbox checkbox-primary"
        checked={done}
        disabled={!target || update.isPending}
        onChange={toggle}
        aria-label={done ? `Reopen “${task.title}”` : `Mark “${task.title}” done`}
        title={
          statuses.data && !target ? 'No done/default status is set up. Ask an admin.' : undefined
        }
      />
    </label>
  )
}

/** Planned hours for one item; saved on blur or Enter. Empty clears it. */
function HoursInput({
  item,
  planId,
  planDate,
}: {
  item: PlanItem
  planId: number
  planDate: string
}) {
  const toast = useToast()
  const update = useUpdatePlanItem(planDate)
  const saved = item.suggested_hours === null ? '' : String(item.suggested_hours)
  const [value, setValue] = useState(saved)
  const [lastSaved, setLastSaved] = useState(saved)
  // Follow changes made elsewhere (e.g. another tab, or a refetch).
  if (saved !== lastSaved) {
    setLastSaved(saved)
    setValue(saved)
  }

  function commit() {
    const text = value.trim()
    if (text === saved) return
    const hours = text === '' ? null : Number(text)
    if (hours !== null && !(HOURS_PATTERN.test(text) && hours > 0 && hours <= 24)) {
      toast.error('Enter between 0.01 and 24 hours (up to 2 decimals)')
      setValue(saved)
      return
    }
    update.mutate(
      { planId, itemId: item.id, hours },
      {
        onError: (error) => {
          toast.error(errorMessage(error))
          setValue(saved)
        },
      },
    )
  }

  return (
    <label className="input input-sm w-28">
      <input
        type="number"
        inputMode="decimal"
        step="0.25"
        min="0.25"
        max="24"
        placeholder="–"
        value={value}
        disabled={update.isPending}
        onChange={(event) => setValue(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur()
        }}
        aria-label={`Planned hours for “${item.task.title}”`}
      />
      <span className="text-base-content/80">h</span>
    </label>
  )
}
