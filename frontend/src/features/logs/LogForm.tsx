/*
 * Create / edit form for a prod log row, rendered inside a Modal. Fields follow the
 * team's sheet: Date, Work set-up, Planned hours, Actual hours, Planned/Unplanned,
 * Category, Project, Activity, Project (For O&M), Reason for deviation and Remarks.
 * Planned and actual hours per day are each capped at WORKDAY_HOURS.
 *
 * A new row can cover several days: with "Until" set, the same row is added on every
 * weekday (Monday to Friday) from Date to Until, all or none (bulk endpoint).
 *
 * The dropdowns are linked (see linkedOptions.ts): changing the category clears a
 * project that is not under it, changing the project clears an activity it does not
 * offer, and "Project (For O&M)" only appears for categories that offer it. A value
 * already on an edited row stays available while its parent is unchanged, even if it
 * has since been deactivated or unlinked (the backend accepts that too).
 *
 * A new row can start from a date (`prefill`, e.g. "Add" on /today), from another row
 * (`copyFrom`, "Copy": same values and remarks, its hours as planned hours, on the next
 * weekday) or from an AI draft (`draft`): required fields the AI left empty are
 * highlighted until filled in, and hours the AI was unsure about are flagged to check.
 *
 * With `onApply` the form edits one AI draft row of a multi-row review instead of
 * saving: submitting hands the checked values back (the review saves all rows at once).
 *
 * Weekly planning: in a locked week (after the Friday deadline) planned hours are read
 * only, except for admins. Rows are Planned unless the user picks Unplanned.
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useMemo, type ComponentProps, type ReactNode } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import type { LogDraftField, LogDraftRow } from '../../api/ai'
import { useCurrentUser } from '../../api/auth'
import { ApiError, errorMessage } from '../../api/client'
import {
  useCreateLog,
  useCreateLogs,
  useUpdateLog,
  type ProdLog,
  type ProdLogCreate,
} from '../../api/logs'
import { useLogOptions, type LogOptions } from '../../api/lookups'
import { usePlanningStatus } from '../../api/planning'
import { DateField } from '../../components/DateInput'
import ErrorAlert from '../../components/ErrorAlert'
import { InputField, SelectField, SubmitButton, TextareaField } from '../../components/FormField'
import { SparklesIcon } from '../../components/icons'
import { SkeletonForm } from '../../components/Skeleton'
import { useToast } from '../../components/toast-context'
import {
  formatDayRange,
  formatDeadline,
  nextWeekday,
  todayIso,
  weekdaysBetween,
} from '../../lib/format'
import { applyFieldErrors } from '../../lib/forms'
import { buildLinked, withCurrent, type Choice, type Linked } from './linkedOptions'

const HOURS_PATTERN = /^\d{1,2}(\.\d{1,2})?$/
const NEED_HOURS = 'Enter planned hours, actual hours, or both'
/** The bulk endpoint's row limit. */
const MAX_DAYS = 31

/** Hours on one row: more than 0, at most the daily cap, up to 2 decimals. */
function hoursField(max: number) {
  return z
    .string()
    .trim()
    .refine(
      (v) => v === '' || (HOURS_PATTERN.test(v) && Number(v) > 0 && Number(v) <= max),
      `Enter between 0.01 and ${max} hours (up to 2 decimals)`,
    )
}

function untilError(from: string, until: string): string | null {
  if (until < from) return 'Choose a day on or after the date'
  const days = weekdaysBetween(from, until).length
  if (days === 0) return 'Saturday and Sunday are skipped: choose a range with a weekday'
  if (days > MAX_DAYS) return `Choose at most ${MAX_DAYS} weekdays`
  return null
}

// Mirrors app/schemas/prod_logs.py. Select values are id strings ("" = none).
function makeSchema(requireProject: boolean, maxHours: number) {
  return z
    .object({
      log_date: z.string().min(1, 'Choose a date'),
      until: z.string(),
      work_setup_id: z.string().min(1, 'Choose a work set-up'),
      planned_hours: hoursField(maxHours),
      hours_spent: hoursField(maxHours),
      category_id: z.string().min(1, 'Choose a category'),
      project_id: z.string(),
      activity_id: z.string().min(1, 'Choose an activity'),
      om_project_id: z.string(),
      description: z.string().trim().max(10000, 'Use at most 10000 characters'),
      deviation_reason_id: z.string(),
      is_planned: z.enum(['planned', 'unplanned']),
    })
    .superRefine((data, ctx) => {
      if (!data.planned_hours && !data.hours_spent) {
        ctx.addIssue({ code: 'custom', path: ['hours_spent'], message: NEED_HOURS })
      }
      if (requireProject && !data.project_id) {
        ctx.addIssue({ code: 'custom', path: ['project_id'], message: 'Choose a project' })
      }
      const message = data.until && data.log_date ? untilError(data.log_date, data.until) : null
      if (message) ctx.addIssue({ code: 'custom', path: ['until'], message })
    })
}
type LogForm = z.infer<ReturnType<typeof makeSchema>>

const FIELDS = [
  'log_date',
  'work_setup_id',
  'planned_hours',
  'hours_spent',
  'category_id',
  'project_id',
  'activity_id',
  'om_project_id',
  'description',
  'deviation_reason_id',
  'is_planned',
] as const

const idOrNull = (value: string) => (value ? Number(value) : null)
const hoursOrNull = (value: string) => (value ? Number(value) : null)
const asString = (value: number | string | null | undefined) =>
  value === null || value === undefined ? '' : String(value)

interface LogFormProps {
  /** null = new log (always the caller's own). */
  log: ProdLog | null
  /** False when an admin edits someone else's log. */
  isOwn: boolean
  /** New log only: start on this date. */
  prefill?: LogPrefill
  /** New log only: start from a copy of this row. */
  copyFrom?: ProdLog
  /** New log only: start from an AI draft row. */
  draft?: DraftValues
  /**
   * Edit an AI draft row without saving: called with the checked values on submit
   * (instead of creating the log), then onDone. Needs `draft`.
   */
  onApply?: (row: DraftValues) => void
  /** Called after a successful save (with the first row of a range), before onDone. */
  onSaved?: (log: ProdLog) => void
  /** Called after saving and on cancel. */
  onDone: () => void
}

export interface LogPrefill {
  logDate: string
}

/** An AI draft row, plus the deviation reason once a user has set one in review. */
export type DraftValues = LogDraftRow & { deviation_reason_id?: number | null }

/** Loads the dropdown options first, so every select is ready when the form mounts. */
export default function LogFormBody(props: LogFormProps) {
  const options = useLogOptions()
  if (options.isPending) return <SkeletonForm fields={8} />
  if (options.error) {
    return (
      <ErrorAlert
        title="Could not load the form options"
        error={options.error}
        onRetry={() => void options.refetch()}
      />
    )
  }
  return <LogFormInner {...props} options={options.data} />
}

const EMPTY = {
  until: '',
  om_project_id: '',
  description: '',
  deviation_reason_id: '',
  planned_hours: '',
  is_planned: 'planned' as const,
}

/** The id of a value on a row, if it is still active ("" otherwise). */
function activeId(ref: { id: number; is_active: boolean } | null): string {
  return ref?.is_active ? String(ref.id) : ''
}

function defaultValues(
  linked: Linked,
  { log, prefill, draft, copyFrom }: Pick<LogFormProps, 'log' | 'prefill' | 'draft' | 'copyFrom'>,
): LogForm {
  if (draft) {
    // The backend only returns active values that fit the linked rules.
    return {
      ...EMPTY,
      log_date: draft.log_date,
      work_setup_id: asString(draft.work_setup_id) || linked.defaultWorkSetupId,
      planned_hours: asString(draft.planned_hours),
      hours_spent: asString(draft.hours_spent),
      category_id: asString(draft.category_id),
      project_id: asString(draft.project_id),
      activity_id: asString(draft.activity_id),
      om_project_id: asString(draft.om_project_id),
      description: draft.description ?? '',
      deviation_reason_id: asString(draft.deviation_reason_id),
      is_planned: draft.is_planned ? 'planned' : 'unplanned',
    }
  }
  if (log) {
    return {
      ...EMPTY,
      log_date: log.log_date,
      work_setup_id: String(log.work_setup.id),
      planned_hours: asString(log.planned_hours),
      hours_spent: asString(log.hours_spent),
      category_id: String(log.category.id),
      project_id: asString(log.project?.id),
      activity_id: String(log.activity.id),
      om_project_id: asString(log.om_project?.id),
      description: log.description ?? '',
      deviation_reason_id: asString(log.deviation_reason?.id),
      is_planned: log.is_planned ? 'planned' : 'unplanned',
    }
  }
  if (copyFrom) {
    // A new row: only active values that still fit together are kept.
    const category = activeId(copyFrom.category)
    const projectId = activeId(copyFrom.project)
    const project = linked.isProjectValid(projectId, category) ? projectId : ''
    const activity = activeId(copyFrom.activity)
    return {
      ...EMPTY,
      log_date: nextWeekday(copyFrom.log_date),
      work_setup_id: activeId(copyFrom.work_setup) || linked.defaultWorkSetupId,
      planned_hours: asString(copyFrom.planned_hours ?? copyFrom.hours_spent),
      hours_spent: '',
      category_id: category,
      project_id: project,
      activity_id: linked.isActivityValid(activity, project) ? activity : '',
      om_project_id: linked.offersOmProject(category) ? activeId(copyFrom.om_project) : '',
      description: copyFrom.description ?? '',
      is_planned: copyFrom.is_planned ? 'planned' : 'unplanned',
    }
  }
  return {
    ...EMPTY,
    log_date: prefill?.logDate ?? todayIso(),
    work_setup_id: linked.defaultWorkSetupId,
    hours_spent: '',
    category_id: '',
    project_id: '',
    activity_id: '',
  }
}

/** A bulk error keyed by row ("rows.2.hours_spent") as a plain field error. */
function withoutRowPrefix(error: unknown): unknown {
  if (!(error instanceof ApiError)) return error
  const fields = Object.fromEntries(
    Object.entries(error.fields).map(([key, message]) => [
      key.replace(/^rows\.\d+\./, ''),
      message,
    ]),
  )
  return new ApiError(error.status, error.code, error.message, fields)
}

const MISSING_HINT: ReactNode = (
  <span className="flex items-center gap-1.5">
    <span className="badge badge-warning badge-sm">Missing</span>
    Not found in your description
  </span>
)

const CHECK_HOURS_HINT: ReactNode = (
  <span className="flex items-center gap-1.5">
    <span className="badge badge-warning badge-sm">Check</span>
    Read as hours per day: the AI was not sure
  </span>
)

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

const hasChoice = (choices: Choice[], id: string) => choices.some((c) => String(c.id) === id)

function LogFormInner({
  log,
  isOwn,
  prefill,
  copyFrom,
  draft,
  onApply,
  onSaved,
  onDone,
  options,
}: LogFormProps & { options: LogOptions }) {
  const toast = useToast()
  const isAdmin = useCurrentUser().data?.role === 'admin'
  const create = useCreateLog()
  const createMany = useCreateLogs()
  const update = useUpdateLog()
  const isPending = create.isPending || createMany.isPending || update.isPending
  const linked = useMemo(() => buildLinked(options), [options])
  // Old rows (from before projects were required) may stay without a project.
  const requireProject = !log || log.project !== null
  const {
    register,
    handleSubmit,
    setError,
    setValue,
    getValues,
    control,
    formState: { errors },
  } = useForm<LogForm>({
    resolver: zodResolver(makeSchema(requireProject, options.workday_hours)),
    defaultValues: defaultValues(linked, { log, prefill, draft, copyFrom }),
  })
  const values = useWatch({ control })

  // ------------------------------------------------------------ linked choices

  const original = {
    category: asString(log?.category.id),
    project: asString(log?.project?.id),
  }
  const projectChoices = (category: string) =>
    withCurrent(linked.projectsFor(category), log?.project, category === original.category)
  const activityChoices = (project: string) =>
    withCurrent(linked.activitiesFor(project), log?.activity, project === original.project)
  const omChoices = (category: string) => {
    const keep = category === original.category && log?.om_project != null
    return linked.offersOmProject(category) || keep
      ? withCurrent(options.om_projects, log?.om_project, keep)
      : []
  }

  /** Clear values that no longer fit after the category or project changed. */
  function cascade(category: string, project: string) {
    const opts = { shouldDirty: true }
    if (project && !hasChoice(projectChoices(category), project)) {
      project = ''
      setValue('project_id', '', opts)
    }
    const activity = getValues('activity_id')
    if (activity && !hasChoice(activityChoices(project), activity)) {
      setValue('activity_id', '', opts)
    }
    const om = getValues('om_project_id')
    if (om && !hasChoice(omChoices(category), om)) setValue('om_project_id', '', opts)
  }

  const category = values.category_id ?? ''
  const project = values.project_id ?? ''
  const projects = projectChoices(category)
  const activities = activityChoices(project)
  const omProjects = omChoices(category)
  const workSetups = withCurrent(options.work_setups, log?.work_setup)
  const categories = withCurrent(options.categories, log?.category)
  const reasons = withCurrent(options.deviation_reasons, log?.deviation_reason)

  // ------------------------------------------------------------ dates and planning lock

  const logDate = values.log_date ?? ''
  const until = values.until ?? ''
  const rangeDays =
    !log && !onApply && logDate && until && !untilError(logDate, until)
      ? weekdaysBetween(logDate, until)
      : []
  const isRange = rangeDays.length > 1 || (rangeDays.length === 1 && rangeDays[0] !== logDate)

  const week = usePlanningStatus(logDate || undefined, /^\d{4}-\d{2}-\d{2}$/.test(logDate))
  const plannedLocked = !isAdmin && week.data !== undefined && !week.data.is_open
  const lockHint = week.data && !week.data.is_open && (
    <>
      Planning for this week closed {formatDeadline(week.data.deadline)}.{' '}
      {isAdmin ? 'You can still change it as an admin.' : 'Planned hours can no longer change.'}
    </>
  )

  const planned = values.planned_hours?.trim() ?? ''
  const actual = values.hours_spent?.trim() ?? ''
  const deviates = planned !== '' && actual !== '' && Number(planned) !== Number(actual)
  const maxHours = String(options.workday_hours)

  // ------------------------------------------------------------ AI draft hints

  /**
   * Highlight for a required field the AI draft left empty, until it is filled in, and
   * for drafted hours the AI was unsure about, until they are changed.
   */
  function missing(
    field: LogDraftField,
    kind: 'input' | 'select',
    hoursField?: 'planned_hours' | 'hours_spent',
  ) {
    if (!draft?.missing_fields.includes(field)) return {}
    if (field === 'hours') {
      const draftPlanned = asString(draft.planned_hours)
      const draftActual = asString(draft.hours_spent)
      if (draftPlanned || draftActual) {
        const unchanged = planned === draftPlanned && actual === draftActual
        const holdsHours = (hoursField === 'planned_hours' ? draftPlanned : draftActual) !== ''
        return unchanged && holdsHours
          ? { hint: CHECK_HOURS_HINT, className: `${kind}-warning` }
          : {}
      }
      if (planned || actual || errors.hours_spent) return {}
    } else if (values[field]?.trim() || errors[field]) {
      return {}
    }
    return { hint: MISSING_HINT, className: `${kind}-warning` }
  }

  // ------------------------------------------------------------ submit

  function onSubmit(data: LogForm) {
    const body: ProdLogCreate = {
      log_date: data.log_date,
      work_setup_id: Number(data.work_setup_id),
      planned_hours: hoursOrNull(data.planned_hours),
      hours_spent: hoursOrNull(data.hours_spent),
      category_id: Number(data.category_id),
      activity_id: Number(data.activity_id),
      om_project_id: omProjects.length ? idOrNull(data.om_project_id) : null,
      description: data.description || null,
      deviation_reason_id: idOrNull(data.deviation_reason_id),
      is_planned: data.is_planned === 'planned',
      project_id: idOrNull(data.project_id),
    }
    const onError = (error: unknown) => {
      const plain = withoutRowPrefix(error)
      if (!applyFieldErrors(plain, setError, FIELDS)) toast.error(errorMessage(plain))
    }
    if (onApply && draft) {
      onApply({
        log_date: data.log_date,
        is_planned: data.is_planned === 'planned',
        work_setup_id: Number(data.work_setup_id),
        planned_hours: hoursOrNull(data.planned_hours),
        hours_spent: hoursOrNull(data.hours_spent),
        category_id: Number(data.category_id),
        project_id: idOrNull(data.project_id),
        activity_id: Number(data.activity_id),
        om_project_id: body.om_project_id ?? null,
        description: data.description || null,
        deviation_reason_id: idOrNull(data.deviation_reason_id),
        missing_fields: [],
      })
      onDone()
      return
    }
    const finish = (saved: ProdLog, message: string) => {
      onSaved?.(saved)
      toast.success(message)
      onDone()
    }

    if (log) {
      // An old row without a project keeps it empty unless one is chosen.
      const { project_id, ...rest } = body
      update.mutate(
        { id: log.id, ...rest, ...(project_id !== null ? { project_id } : {}) },
        { onSuccess: (saved) => finish(saved, `Saved “${saved.activity.label}”`), onError },
      )
    } else if (isRange) {
      createMany.mutate(
        rangeDays.map((day) => ({ ...body, log_date: day })),
        {
          onSuccess: (result) => {
            const first = result.items[0]
            if (first) {
              finish(first, `Added “${first.activity.label}” on ${plural(result.created, 'day')}`)
            }
          },
          onError,
        },
      )
    } else {
      create.mutate(body, {
        onSuccess: (saved) => finish(saved, `Added “${saved.activity.label}”`),
        onError,
      })
    }
  }

  const categoryField = register('category_id')
  const projectField = register('project_id')

  return (
    <form onSubmit={(e) => void handleSubmit(onSubmit)(e)} noValidate>
      {!isOwn && log && (
        <p className="mb-2 rounded-box bg-base-200 px-3 py-2 text-sm">
          Editing a log by <strong>{log.user.username}</strong>. You will be shown as the last
          editor.
        </p>
      )}
      {draft && !onApply && (
        <div role="status" className="alert alert-info mb-2 text-sm">
          <SparklesIcon className="size-4" />
          <span>Drafted by AI. Check every field before saving.</span>
        </div>
      )}
      {copyFrom && (
        <p className="mb-2 rounded-box bg-base-200 px-3 py-2 text-sm">
          A copy of <strong>{copyFrom.activity.label}</strong>. Pick the day (or days with “Until”),
          check the hours, and add it.
        </p>
      )}
      <div className="grid grid-cols-1 gap-x-3 md:grid-cols-2">
        <Controller
          control={control}
          name="log_date"
          render={({ field }) => (
            <DateField
              label="Date"
              wrapperClassName={log || onApply ? 'md:col-span-2' : undefined}
              error={errors.log_date?.message}
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
              ref={field.ref}
            />
          )}
        />
        {!log && !onApply && (
          <Controller
            control={control}
            name="until"
            render={({ field }) => (
              <DateField
                label="Until (optional)"
                placeholder="Only this day"
                clearable
                min={logDate || undefined}
                error={errors.until?.message}
                hint={
                  isRange
                    ? `Adds this row on ${plural(rangeDays.length, 'weekday')}, ${formatDayRange(
                        rangeDays[0] ?? logDate,
                        rangeDays.at(-1) ?? logDate,
                      )}.`
                    : 'Add the same row on every weekday up to this date.'
                }
                value={field.value}
                onChange={field.onChange}
                onBlur={field.onBlur}
                ref={field.ref}
              />
            )}
          />
        )}
        <ChoiceSelect
          label="Work set-up"
          choices={workSetups}
          emptyLabel={workSetups.length ? undefined : 'No work set-ups yet'}
          error={errors.work_setup_id?.message}
          {...missing('work_setup_id', 'select')}
          {...register('work_setup_id')}
        />
        <SelectField
          label="Planned / Unplanned"
          error={errors.is_planned?.message}
          {...register('is_planned')}
        >
          <option value="planned">Planned</option>
          <option value="unplanned">Unplanned</option>
        </SelectField>
        <InputField
          label={isRange ? 'Planned hours (per day)' : 'Planned hours'}
          type="number"
          inputMode="decimal"
          step="0.25"
          min="0.25"
          max={maxHours}
          readOnly={plannedLocked}
          className={plannedLocked ? 'bg-base-200' : ''}
          error={errors.planned_hours?.message}
          {...missing('hours', 'input', 'planned_hours')}
          {...(lockHint ? { hint: lockHint } : {})}
          {...register('planned_hours')}
        />
        <InputField
          label={isRange ? 'Actual hours (per day)' : 'Actual hours'}
          type="number"
          inputMode="decimal"
          step="0.25"
          min="0.25"
          max={maxHours}
          error={errors.hours_spent?.message}
          {...missing('hours', 'input', 'hours_spent')}
          {...register('hours_spent')}
        />
        <ChoiceSelect
          label="Category"
          choices={categories}
          emptyLabel="Choose a category"
          error={errors.category_id?.message}
          {...missing('category_id', 'select')}
          {...categoryField}
          onChange={(event) => {
            void categoryField.onChange(event)
            cascade(event.target.value, getValues('project_id'))
          }}
        />
        <ChoiceSelect
          label="Project"
          choices={projects}
          emptyLabel={category ? 'Choose a project' : 'Choose a category first'}
          hint={
            category && projects.length === 0 ? 'No projects under this category yet.' : undefined
          }
          error={errors.project_id?.message}
          {...missing('project_id', 'select')}
          {...projectField}
          onChange={(event) => {
            void projectField.onChange(event)
            cascade(getValues('category_id'), event.target.value)
          }}
        />
        <ChoiceSelect
          label="Activity"
          choices={activities}
          emptyLabel={project ? 'Choose an activity' : 'Choose a project first'}
          hint={
            project && activities.length === 0
              ? 'This project offers no activities yet. Ask an admin to set its activity group.'
              : undefined
          }
          error={errors.activity_id?.message}
          {...missing('activity_id', 'select')}
          {...register('activity_id')}
        />
        {omProjects.length > 0 && (
          <ChoiceSelect
            label="Project (For O&M) (optional)"
            choices={omProjects}
            emptyLabel="None"
            error={errors.om_project_id?.message}
            {...register('om_project_id')}
          />
        )}
      </div>
      <ChoiceSelect
        label="Reason for deviation (optional)"
        choices={reasons}
        emptyLabel="None"
        hint={deviates ? 'Actual hours differ from planned.' : undefined}
        error={errors.deviation_reason_id?.message}
        {...register('deviation_reason_id')}
      />
      <TextareaField
        label="Remarks (optional)"
        rows={2}
        error={errors.description?.message}
        {...register('description')}
      />
      <div className="modal-action">
        <button type="button" className="btn btn-ghost" onClick={onDone}>
          Cancel
        </button>
        <SubmitButton isPending={isPending}>
          {onApply
            ? 'Done'
            : log
              ? 'Save'
              : isRange
                ? `Add ${plural(rangeDays.length, 'row')}`
                : 'Add log'}
        </SubmitButton>
      </div>
    </form>
  )
}

type ChoiceSelectProps = Omit<ComponentProps<typeof SelectField>, 'children'> & {
  choices: Choice[]
  /** Adds a first option with value "" (for unset or optional fields). */
  emptyLabel?: string
}

function ChoiceSelect({ choices, emptyLabel, ...props }: ChoiceSelectProps) {
  return (
    <SelectField {...props}>
      {emptyLabel !== undefined && <option value="">{emptyLabel}</option>}
      {choices.map((choice) => (
        <option key={choice.id} value={choice.id}>
          {choice.note ? `${choice.label} (${choice.note})` : choice.label}
        </option>
      ))}
    </SelectField>
  )
}
