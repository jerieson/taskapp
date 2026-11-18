/*
 * /today, "Plan week" tab: the planned rows of one week, Monday to Friday (?week=,
 * default next week), with the deadline countdown and "Copy this week's plan" (the week
 * before into this one, by weekday; days that would pass the workday are skipped). A
 * single row is copied to other days with its "Copy" button (the log form, prefilled).
 * A locked week is read-only for planned hours (admins excepted).
 */
import { useState } from 'react'

import { useCurrentUser } from '../../api/auth'
import { errorMessage } from '../../api/client'
import {
  useCopyLogs,
  useDeleteLog,
  useLogsInRange,
  type CopyLogs,
  type ProdLogItem,
} from '../../api/logs'
import { usePlanningStatus, type PlanningStatus } from '../../api/planning'
import AsyncState from '../../components/AsyncState'
import ColorDot from '../../components/ColorDot'
import ConfirmModal from '../../components/ConfirmModal'
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  CopyIcon,
  PencilIcon,
  PlusIcon,
  TrashIcon,
} from '../../components/icons'
import { SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/toast-context'
import {
  formatDay,
  formatDayRange,
  formatDayWithWeekday,
  formatHours,
  formatWeekday,
  mondayOf,
  shiftDay,
  todayIso,
} from '../../lib/format'
import LogFormModal, { type LogModalState } from '../logs/LogFormModal'
import { logHours, logLabel } from '../logs/logText'
import { copySummary, useWeekOpen } from './planning'
import { DeadlineCountdown } from './PlanningParts'

interface PlanWeekViewProps {
  /** Any date in the week; undefined = next week. */
  week: string | undefined
  onWeekChange: (monday: string | undefined) => void
}

function WeekSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-hidden="true">
      <SkeletonCard lines={2} />
      <SkeletonCard lines={2} />
      <SkeletonCard lines={2} />
    </div>
  )
}

export default function PlanWeekView({ week, onWeekChange }: PlanWeekViewProps) {
  const status = usePlanningStatus(week)
  return (
    <AsyncState query={status} skeleton={<WeekSkeleton />}>
      {() => <WeekPlan status={status.data!} isDefault={!week} onWeekChange={onWeekChange} />}
    </AsyncState>
  )
}

function WeekPlan({
  status,
  isDefault,
  onWeekChange,
}: {
  status: PlanningStatus
  isDefault: boolean
  onWeekChange: (monday: string | undefined) => void
}) {
  const toast = useToast()
  const isAdmin = useCurrentUser().data?.role === 'admin'
  const logs = useLogsInRange(status.week_start, status.week_end)
  const copy = useCopyLogs()
  const remove = useDeleteLog()
  const weekOpen = useWeekOpen(status)
  const canPlan = weekOpen || isAdmin

  const [modal, setModal] = useState<LogModalState | null>(null)
  const [deleting, setDeleting] = useState<ProdLogItem | null>(null)
  const [copyingWeek, setCopyingWeek] = useState(false)

  const previousWeek = shiftDay(status.week_start, -7)
  const isThisWeek = previousWeek === mondayOf(todayIso())
  const copyWeekLabel = isThisWeek
    ? 'Copy this week’s plan'
    : `Copy week of ${formatDay(previousWeek)}`

  function runCopy(body: CopyLogs, close: () => void) {
    copy.mutate(body, {
      onSuccess: (result) => {
        if (result.created > 0) toast.success(copySummary(result))
        else toast.error(copySummary(result))
        close()
      },
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  function confirmDelete() {
    if (!deleting) return
    const log = deleting
    remove.mutate(log.id, {
      onSuccess: () => toast.success(`“${logLabel(log)}” deleted`),
      onError: (error) => toast.error(errorMessage(error)),
      onSettled: () => setDeleting(null),
    })
  }

  const rowsByDay = new Map<string, ProdLogItem[]>()
  for (const log of logs.data ?? []) {
    rowsByDay.set(log.log_date, [...(rowsByDay.get(log.log_date) ?? []), log])
  }
  const workday = status.workday_hours

  return (
    <>
      <section
        aria-label="Week"
        className="mb-4 flex flex-col gap-3 rounded-box border border-base-300 bg-base-100 p-4"
      >
        <div className="flex flex-wrap items-center gap-2">
          <div className="join">
            <button
              type="button"
              className="btn join-item btn-square btn-sm"
              onClick={() => onWeekChange(shiftDay(status.week_start, -7))}
              aria-label="Previous week"
            >
              <ChevronLeftIcon />
            </button>
            <button
              type="button"
              className="btn join-item btn-square btn-sm"
              onClick={() => onWeekChange(shiftDay(status.week_start, 7))}
              aria-label="Next week"
            >
              <ChevronRightIcon />
            </button>
          </div>
          <h2 className="font-semibold" aria-live="polite">
            {formatDayRange(status.week_start, status.week_end)}
          </h2>
          {!isDefault && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => onWeekChange(undefined)}
            >
              Next week
            </button>
          )}
        </div>
        <DeadlineCountdown week={status} />
        <p className="text-sm">
          <span className="font-semibold tabular-nums">{formatHours(status.total)}</span> planned of{' '}
          <span className="tabular-nums">{formatHours(workday * 5)}</span> ({formatHours(workday)} a
          day)
        </p>
        {weekOpen && (
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn btn-sm" onClick={() => setCopyingWeek(true)}>
              <CopyIcon className="size-4" />
              {copyWeekLabel}
            </button>
          </div>
        )}
      </section>

      <AsyncState query={logs} skeleton={<WeekSkeleton />}>
        {() => (
          <ol className="flex flex-col gap-3" aria-label="Days of the week">
            {status.days.map((day) => (
              <PlanDay
                key={day.date}
                date={day.date}
                planned={day.planned_hours}
                workday={workday}
                rows={rowsByDay.get(day.date) ?? []}
                canPlan={canPlan}
                onAdd={() =>
                  setModal({ kind: 'new', date: day.date, title: 'Add planned activity' })
                }
                onEdit={(log) => setModal({ kind: 'edit', log })}
                onCopy={(log) => setModal({ kind: 'copy', log })}
                onDelete={setDeleting}
              />
            ))}
          </ol>
        )}
      </AsyncState>

      <LogFormModal state={modal} onClose={() => setModal(null)} />

      <ConfirmModal
        open={copyingWeek}
        title={copyWeekLabel}
        confirmLabel="Copy"
        tone="primary"
        isPending={copy.isPending}
        onConfirm={() =>
          runCopy({ from_week: previousWeek, to_dates: status.days.map((d) => d.date) }, () =>
            setCopyingWeek(false),
          )
        }
        onCancel={() => setCopyingWeek(false)}
      >
        <p>
          Your rows from {formatDayRange(previousWeek, shiftDay(previousWeek, 4))} are added to{' '}
          {formatDayRange(status.week_start, status.week_end)} as planned rows, day by day (Monday
          to Monday, and so on). Planned hours come from the planned hours, or the actual hours when
          none were planned.
        </p>
        <p className="mt-2 text-sm text-base-content/80">
          Rows already planned stay. Days that would pass {formatHours(workday)} planned are
          skipped.
        </p>
      </ConfirmModal>

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

interface PlanDayProps {
  date: string
  planned: number
  workday: number
  rows: ProdLogItem[]
  canPlan: boolean
  onAdd: () => void
  onEdit: (log: ProdLogItem) => void
  onCopy: (log: ProdLogItem) => void
  onDelete: (log: ProdLogItem) => void
}

function PlanDay({
  date,
  planned,
  workday,
  rows,
  canPlan,
  onAdd,
  onEdit,
  onCopy,
  onDelete,
}: PlanDayProps) {
  return (
    <li className="overflow-hidden rounded-box border border-base-300 bg-base-100">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-base-300 bg-base-200 px-4 py-2">
        <h3 className="font-semibold">{formatDayWithWeekday(date)}</h3>
        <span className="flex items-center gap-2 text-sm">
          {planned > workday && <span className="badge badge-warning badge-sm">Over workday</span>}
          <span className="badge badge-primary font-semibold tabular-nums">
            <span className="sr-only">Planned: </span>
            {formatHours(planned)}
          </span>
          {canPlan && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={onAdd}
              aria-label={`Add a planned activity on ${formatWeekday(date)}`}
            >
              <PlusIcon className="size-4" />
              Add
            </button>
          )}
        </span>
      </header>
      {rows.length === 0 ? (
        <p className="px-4 py-3 text-sm text-base-content/80">Nothing planned.</p>
      ) : (
        <ul className="divide-y divide-base-300">
          {rows.map((log) => (
            <li key={log.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-1.5 font-medium break-words">
                  <ColorDot color={log.activity.color} />
                  {log.activity.label}
                </p>
                <p className="text-xs break-words text-base-content/80">
                  {log.project?.name ?? 'No project'} · {log.category.label}
                </p>
              </div>
              <span className="font-semibold tabular-nums">
                {log.planned_hours === null ? (
                  <span className="text-base-content/80">
                    —<span className="sr-only">no planned hours</span>
                  </span>
                ) : (
                  formatHours(log.planned_hours)
                )}
              </span>
              <span className="flex gap-1">
                <button
                  type="button"
                  className="btn btn-ghost btn-sm btn-square"
                  onClick={() => onEdit(log)}
                  aria-label={`Edit ${logLabel(log)}`}
                >
                  <PencilIcon className="size-4" />
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm btn-square"
                  onClick={() => onCopy(log)}
                  aria-label={`Copy ${logLabel(log)} to other days`}
                >
                  <CopyIcon className="size-4" />
                </button>
                {(canPlan || log.planned_hours === null) && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn-square"
                    onClick={() => onDelete(log)}
                    aria-label={`Delete ${logLabel(log)}`}
                  >
                    <TrashIcon className="size-4" />
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}
