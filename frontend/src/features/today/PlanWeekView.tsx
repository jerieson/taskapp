/*
 * /today, "Plan week" tab: the planned rows of one week, Monday to Friday (?week=,
 * default next week), with the deadline countdown, "Copy this week's plan" (the week
 * before into this one, by weekday) and "Copy a day" (one day into chosen days).
 * Copies are planned rows; days that would pass 24 planned hours are skipped. A locked
 * week is read-only for planned hours (admins excepted).
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { useCurrentUser } from '../../api/auth'
import { errorMessage } from '../../api/client'
import {
  useCopyLogs,
  useDeleteLog,
  useLogsInRange,
  type CopyLogs,
  type ProdLog,
  type ProdLogItem,
} from '../../api/logs'
import { usePlanningStatus, type PlanningStatus } from '../../api/planning'
import AsyncState from '../../components/AsyncState'
import ColorDot from '../../components/ColorDot'
import ConfirmModal from '../../components/ConfirmModal'
import { InputField, SubmitButton } from '../../components/FormField'
import {
  AlertIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CopyIcon,
  PencilIcon,
  PlusIcon,
  TrashIcon,
} from '../../components/icons'
import Modal from '../../components/Modal'
import { SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/toast-context'
import {
  formatDay,
  formatDayRange,
  formatDayWithWeekday,
  formatHours,
  formatShortDay,
  formatWeekday,
  mondayOf,
  shiftDay,
  todayIso,
} from '../../lib/format'
import LogFormBody from '../logs/LogForm'
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

  // undefined = closed; {date} = new row on that date; {log} = edit.
  const [editing, setEditing] = useState<{ date: string; log: ProdLog | null } | undefined>()
  const [deleting, setDeleting] = useState<ProdLogItem | null>(null)
  const [copyingWeek, setCopyingWeek] = useState(false)
  const [copyingDay, setCopyingDay] = useState(false)

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
            <button type="button" className="btn btn-sm" onClick={() => setCopyingDay(true)}>
              <CopyIcon className="size-4" />
              Copy a day to the week
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
                onAdd={() => setEditing({ date: day.date, log: null })}
                onEdit={(log) => setEditing({ date: day.date, log })}
                onDelete={setDeleting}
              />
            ))}
          </ol>
        )}
      </AsyncState>

      <Modal
        open={editing !== undefined}
        title={editing?.log ? 'Edit row' : 'Add planned activity'}
        onClose={() => setEditing(undefined)}
      >
        {editing && (
          <LogFormBody
            log={editing.log}
            isOwn
            prefill={{ logDate: editing.date }}
            onDone={() => setEditing(undefined)}
          />
        )}
      </Modal>

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
          Rows already planned stay. Days that would pass 24 planned hours are skipped.
        </p>
      </ConfirmModal>

      <Modal open={copyingDay} title="Copy a day to the week" onClose={() => setCopyingDay(false)}>
        {copyingDay && (
          <CopyDayForm
            days={status.days.map((d) => d.date)}
            isPending={copy.isPending}
            onSubmit={(body) => runCopy(body, () => setCopyingDay(false))}
            onCancel={() => setCopyingDay(false)}
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

interface PlanDayProps {
  date: string
  planned: number
  workday: number
  rows: ProdLogItem[]
  canPlan: boolean
  onAdd: () => void
  onEdit: (log: ProdLogItem) => void
  onDelete: (log: ProdLogItem) => void
}

function PlanDay({ date, planned, workday, rows, canPlan, onAdd, onEdit, onDelete }: PlanDayProps) {
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
                  {log.title && ` · ${log.title}`}
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

// ---------------------------------------------------------------- copy a day

const copyDaySchema = z.object({
  from_date: z.string().min(1, 'Choose a day to copy'),
  to_dates: z.array(z.string()).min(1, 'Choose at least one day'),
})
type CopyDayValues = z.infer<typeof copyDaySchema>

function CopyDayForm({
  days,
  isPending,
  onSubmit,
  onCancel,
}: {
  days: string[]
  isPending: boolean
  onSubmit: (body: CopyLogs) => void
  onCancel: () => void
}) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CopyDayValues>({
    resolver: zodResolver(copyDaySchema),
    defaultValues: { from_date: todayIso(), to_dates: days },
  })

  return (
    <form
      onSubmit={(e) =>
        void handleSubmit((data) =>
          onSubmit({
            from_date: data.from_date,
            to_dates: data.to_dates.filter((d) => d !== data.from_date),
          }),
        )(e)
      }
      noValidate
    >
      <InputField
        label="Copy the rows of"
        type="date"
        error={errors.from_date?.message}
        {...register('from_date')}
      />
      <fieldset className="fieldset">
        <legend className="fieldset-legend">To these days</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {days.map((day) => (
            <label key={day} className="label min-h-11 cursor-pointer gap-2 text-base-content">
              <input
                type="checkbox"
                className="checkbox checkbox-primary"
                value={day}
                {...register('to_dates')}
              />
              {formatWeekday(day)} {formatShortDay(day)}
            </label>
          ))}
        </div>
        {errors.to_dates && (
          <p className="flex items-center gap-1.5 text-sm text-base-content" role="alert">
            <span className="inline-flex rounded-full bg-error p-0.5 text-error-content">
              <AlertIcon className="size-3" />
            </span>
            {errors.to_dates.message}
          </p>
        )}
      </fieldset>
      <p className="mt-2 text-sm text-base-content/80">
        Rows are added as planned rows: planned hours come from the planned hours, or the actual
        hours when none were planned. Days that would pass 24 planned hours are skipped.
      </p>
      <div className="modal-action">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
        <SubmitButton isPending={isPending}>Copy</SubmitButton>
      </div>
    </form>
  )
}
