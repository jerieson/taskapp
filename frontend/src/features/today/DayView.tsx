/*
 * /today, "Day" tab: the rows of one day (?date=, default today), planned against
 * actual, with totals against WORKDAY_HOURS. Actual hours are filled in inline, or
 * copied from the planned hours with one click. Rows are edited and deleted here too;
 * in a locked week planned hours are read-only and planned rows can't be deleted
 * (admins excepted).
 */
import { useState, type FormEvent } from 'react'

import { useCurrentUser } from '../../api/auth'
import { errorMessage } from '../../api/client'
import {
  useDeleteLog,
  useLogsInRange,
  useUpdateLog,
  type ProdLog,
  type ProdLogItem,
} from '../../api/logs'
import { usePlanningStatus } from '../../api/planning'
import AsyncState from '../../components/AsyncState'
import ColorDot from '../../components/ColorDot'
import ConfirmModal from '../../components/ConfirmModal'
import EmptyState from '../../components/EmptyState'
import { CalendarIcon, LockIcon, PencilIcon, PlusIcon, TrashIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import { SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/toast-context'
import { formatDay, formatHours, todayIso } from '../../lib/format'
import AiLogEntry from '../ai/AiLogEntry'
import LogFormBody from '../logs/LogForm'
import { logHours, logLabel } from '../logs/logText'
import DateNav from './DateNav'
import { useWeekOpen } from './planning'

const HOURS_PATTERN = /^\d{1,2}(\.\d{1,2})?$/

function sum(values: (number | null)[]): number {
  return values.reduce<number>((total, v) => total + (v ?? 0), 0)
}

function DaySummary({ rows, workday }: { rows: ProdLogItem[]; workday: number }) {
  const planned = sum(rows.map((r) => r.planned_hours))
  const actual = sum(rows.map((r) => r.hours_spent))
  return (
    <section
      aria-label="Day totals"
      className="mb-4 rounded-box border border-base-300 bg-base-100 p-4"
    >
      <dl className="grid grid-cols-3 gap-3 text-center sm:text-left">
        <div>
          <dt className="text-xs text-base-content/80">Planned</dt>
          <dd className="text-xl font-semibold tabular-nums">{formatHours(planned)}</dd>
        </div>
        <div>
          <dt className="text-xs text-base-content/80">Actual</dt>
          <dd className="text-xl font-semibold tabular-nums">{formatHours(actual)}</dd>
        </div>
        <div>
          <dt className="text-xs text-base-content/80">Workday</dt>
          <dd className="text-xl font-semibold tabular-nums">{formatHours(workday)}</dd>
        </div>
      </dl>
      <progress
        className="progress progress-primary mt-3 w-full"
        value={Math.min(actual, workday)}
        max={workday}
        aria-label={`${formatHours(actual)} of ${formatHours(workday)} actual`}
      />
      {planned > workday && (
        <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <span className="badge badge-warning badge-sm">Over workday</span>
          Planned hours are above the {formatHours(workday)} workday.
        </p>
      )}
    </section>
  )
}

/** Inline actual hours: saved on Enter or when the field loses focus. */
function ActualHoursInput({ log }: { log: ProdLogItem }) {
  const toast = useToast()
  const update = useUpdateLog()
  const [value, setValue] = useState(log.hours_spent === null ? '' : String(log.hours_spent))
  const [error, setError] = useState<string | null>(null)
  const label = logLabel(log)

  function commit(event?: FormEvent) {
    event?.preventDefault()
    const trimmed = value.trim()
    const next = trimmed === '' ? null : Number(trimmed)
    if (next === log.hours_spent) return setError(null)
    if (next !== null && !(HOURS_PATTERN.test(trimmed) && next > 0 && next <= 24)) {
      return setError('0.01 to 24 h')
    }
    if (next === null && log.planned_hours === null) return setError('Enter hours')
    setError(null)
    update.mutate(
      { id: log.id, hours_spent: next },
      {
        onSuccess: () => toast.success(`Saved actual hours for “${label}”`),
        onError: (err) => {
          toast.error(errorMessage(err))
          setValue(log.hours_spent === null ? '' : String(log.hours_spent))
        },
      },
    )
  }

  return (
    <form onSubmit={commit} noValidate className="flex flex-col items-end">
      <label className={`input input-sm w-28 ${error ? 'input-error' : ''}`}>
        <span className="sr-only">Actual hours for {label}</span>
        <input
          type="number"
          inputMode="decimal"
          step="0.25"
          min="0.25"
          max="24"
          placeholder="Actual"
          value={value}
          disabled={update.isPending}
          aria-invalid={error ? true : undefined}
          onChange={(event) => setValue(event.target.value)}
          onBlur={() => commit()}
          className="tabular-nums"
        />
        <span className="text-base-content/80" aria-hidden="true">
          h
        </span>
      </label>
      {error && (
        <span className="mt-0.5 text-xs" role="alert">
          {error}
        </span>
      )}
    </form>
  )
}

interface RowProps {
  log: ProdLogItem
  plannedLocked: boolean
  canDelete: boolean
  onEdit: () => void
  onDelete: () => void
}

function TodayRow({ log, plannedLocked, canDelete, onEdit, onDelete }: RowProps) {
  const toast = useToast()
  const update = useUpdateLog()
  const edited = log.updated_by.id !== log.user.id
  const canMatch = log.planned_hours !== null && log.hours_spent !== log.planned_hours

  function matchPlanned() {
    update.mutate(
      { id: log.id, hours_spent: log.planned_hours },
      {
        onSuccess: () => toast.success(`Actual = planned for “${logLabel(log)}”`),
        onError: (err) => toast.error(errorMessage(err)),
      },
    )
  }

  return (
    <li className="flex flex-col gap-3 rounded-box border border-base-300 bg-base-100 p-4 sm:flex-row sm:items-start">
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-1.5 font-medium break-words">
          <ColorDot color={log.activity.color} />
          {log.activity.label}
        </p>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-base-content/80">
          {log.project && <span className="break-words">{log.project.name}</span>}
          {log.project && <span aria-hidden="true">·</span>}
          <span>{log.category.label}</span>
          {log.om_project && <span className="break-words">· O&M: {log.om_project.label}</span>}
          {log.task && <span className="break-all">· Task: {log.task.title}</span>}
        </p>
        {log.title && <p className="mt-1 text-sm break-words">{log.title}</p>}
        <p className="mt-1.5 flex flex-wrap gap-1.5">
          <span className="badge badge-sm badge-outline">{log.work_setup.label}</span>
          {!log.is_planned && <span className="badge badge-sm badge-secondary">Unplanned</span>}
          {edited && (
            <span className="badge badge-sm badge-accent">edited by {log.updated_by.username}</span>
          )}
        </p>
      </div>

      <div className="flex flex-wrap items-start justify-between gap-3 sm:justify-end">
        <div className="flex flex-col text-sm leading-tight">
          <span className="text-xs text-base-content/80">Planned</span>
          <span className="flex h-8 items-center gap-1 font-semibold tabular-nums">
            {log.planned_hours === null ? '—' : formatHours(log.planned_hours)}
            {plannedLocked && log.planned_hours !== null && (
              <LockIcon className="size-3.5" aria-label="Locked" />
            )}
          </span>
        </div>
        <div className="flex flex-col items-end text-sm leading-tight">
          <span className="self-start text-xs text-base-content/80">Actual</span>
          <ActualHoursInput key={`${log.id}-${log.hours_spent}`} log={log} />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 sm:flex-col sm:items-stretch">
        {canMatch && (
          <button
            type="button"
            className="btn btn-sm btn-primary"
            disabled={update.isPending}
            onClick={matchPlanned}
          >
            Actual = planned
          </button>
        )}
        <div className="flex gap-2">
          <button type="button" className="btn btn-sm" onClick={onEdit}>
            <PencilIcon className="size-4" />
            Edit
          </button>
          {canDelete && (
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={onDelete}
              aria-label={`Delete ${logLabel(log)}`}
            >
              <TrashIcon className="size-4" />
            </button>
          )}
        </div>
      </div>
    </li>
  )
}

function DaySkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-hidden="true">
      <SkeletonCard lines={1} />
      <SkeletonCard lines={2} />
      <SkeletonCard lines={2} />
    </div>
  )
}

export default function DayView({
  date,
  onDateChange,
}: {
  date: string
  onDateChange: (date: string) => void
}) {
  const toast = useToast()
  const isAdmin = useCurrentUser().data?.role === 'admin'
  const status = usePlanningStatus(date)
  const logs = useLogsInRange(date, date)
  const remove = useDeleteLog()
  // undefined = closed, null = new row, ProdLog = edit.
  const [editing, setEditing] = useState<ProdLog | null | undefined>(undefined)
  const [deleting, setDeleting] = useState<ProdLogItem | null>(null)

  const weekOpen = useWeekOpen(status.data)
  const plannedLocked = status.data !== undefined && !weekOpen
  const rows = logs.data ?? []
  const isToday = date === todayIso()

  function confirmDelete() {
    if (!deleting) return
    const log = deleting
    remove.mutate(log.id, {
      onSuccess: () => toast.success(`“${logLabel(log)}” deleted`),
      onError: (error) => toast.error(errorMessage(error)),
      onSettled: () => setDeleting(null),
    })
  }

  const addButton = (
    <button type="button" className="btn btn-primary" onClick={() => setEditing(null)}>
      <PlusIcon />
      {weekOpen ? 'Add planned activity' : 'Add unplanned activity'}
    </button>
  )

  return (
    <>
      <AiLogEntry className="mb-4" />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <DateNav value={date} onChange={onDateChange} />
        {addButton}
      </div>

      <AsyncState
        query={logs}
        isEmpty={rows.length === 0}
        skeleton={<DaySkeleton />}
        empty={
          <EmptyState
            icon={<CalendarIcon className="size-6" />}
            title={isToday ? 'Nothing planned or logged today' : 'Nothing planned or logged'}
            description="Plan your week ahead on “Plan week”, or add what you worked on."
            action={addButton}
          />
        }
      >
        {() => (
          <>
            <DaySummary rows={rows} workday={status.data?.workday_hours ?? 8} />
            <ul className="flex flex-col gap-3" aria-label="Rows for this day">
              {rows.map((log) => (
                <TodayRow
                  key={log.id}
                  log={log}
                  plannedLocked={plannedLocked && !isAdmin}
                  canDelete={isAdmin || !log.is_planned || weekOpen}
                  onEdit={() => setEditing(log)}
                  onDelete={() => setDeleting(log)}
                />
              ))}
            </ul>
          </>
        )}
      </AsyncState>

      <Modal
        open={editing !== undefined}
        title={editing ? 'Edit row' : weekOpen ? 'Add planned activity' : 'Add unplanned activity'}
        onClose={() => setEditing(undefined)}
      >
        {editing !== undefined && (
          <LogFormBody
            log={editing}
            isOwn
            prefill={{ logDate: date }}
            onDone={() => setEditing(undefined)}
          />
        )}
      </Modal>

      <ConfirmModal
        open={deleting !== null}
        title="Delete row?"
        confirmLabel="Delete"
        isPending={remove.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setDeleting(null)}
      >
        {deleting && (
          <p>
            <strong className="break-words">{logLabel(deleting)}</strong> ({logHours(deleting)} on{' '}
            {formatDay(deleting.log_date)}) will be deleted. This cannot be undone.
          </p>
        )}
      </ConfirmModal>
    </>
  )
}
