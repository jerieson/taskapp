/*
 * Create / edit form for a prod log row, rendered inside a Modal. Fields follow the
 * team's sheet: Date, Work set-up, Planned hours, Actual hours, Category, Project,
 * Activity, Project (For O&M), then Task, Note, Remarks and Reason for deviation.
 *
 * The dropdowns are linked (see linkedOptions.ts): changing the category clears a
 * project that is not under it, changing the project clears an activity it does not
 * offer, and "Project (For O&M)" only appears for categories that offer it. A value
 * already on an edited row stays available while its parent is unchanged, even if it
 * has since been deactivated or unlinked (the backend accepts that too).
 *
 * Choosing a task pre-fills the project and category from it (both stay editable).
 * A new log can also start from a date (and task) (`prefill`, e.g. "Add" on /today) or
 * from an AI draft (`draft`): required fields the AI left empty are highlighted until
 * filled in.
 *
 * Weekly planning: in a locked week (after the Friday deadline) planned hours are read
 * only, except for admins. Admins can also override Planned/Unplanned.
 * Only the author can link a task: tasks are private, so an admin editing someone
 * else's log keeps the existing link and does not see the task list.
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useMemo, type ComponentProps, type ReactNode } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import type { LogDraft, LogDraftField } from '../../api/ai'
import { useCurrentUser } from '../../api/auth'
import { errorMessage } from '../../api/client'
import { useCreateLog, useUpdateLog, type ProdLog } from '../../api/logs'
import { useLogOptions, type LogOptions } from '../../api/lookups'
import { usePlanningStatus } from '../../api/planning'
import { useTaskOptions, type Task } from '../../api/tasks'
import ErrorAlert from '../../components/ErrorAlert'
import { SparklesIcon } from '../../components/icons'
import { InputField, SelectField, SubmitButton, TextareaField } from '../../components/FormField'
import { SkeletonForm } from '../../components/Skeleton'
import { useToast } from '../../components/toast-context'
import { formatDeadline, todayIso } from '../../lib/format'
import { applyFieldErrors } from '../../lib/forms'
import { buildLinked, withCurrent, type Choice, type Linked } from './linkedOptions'

const HOURS_PATTERN = /^\d{1,2}(\.\d{1,2})?$/
const HOURS_MESSAGE = 'Enter between 0.01 and 24 hours (up to 2 decimals)'
const NEED_HOURS = 'Enter planned hours, actual hours, or both'

const hoursField = z
  .string()
  .trim()
  .refine(
    (v) => v === '' || (HOURS_PATTERN.test(v) && Number(v) > 0 && Number(v) <= 24),
    HOURS_MESSAGE,
  )

// Mirrors app/schemas/prod_logs.py. Select values are id strings ("" = none).
function makeSchema(requireProject: boolean) {
  return z
    .object({
      log_date: z.string().min(1, 'Choose a date'),
      work_setup_id: z.string().min(1, 'Choose a work set-up'),
      planned_hours: hoursField,
      hours_spent: hoursField,
      category_id: z.string().min(1, 'Choose a category'),
      project_id: z.string(),
      activity_id: z.string().min(1, 'Choose an activity'),
      om_project_id: z.string(),
      task_id: z.string(),
      title: z.string().trim().max(200, 'Use at most 200 characters'),
      description: z.string().trim().max(10000, 'Use at most 10000 characters'),
      deviation_reason: z.string().trim().max(2000, 'Use at most 2000 characters'),
      /** Admin only: "" = automatic (new rows) / unchanged. */
      is_planned: z.enum(['', 'planned', 'unplanned']),
    })
    .superRefine((data, ctx) => {
      if (!data.planned_hours && !data.hours_spent) {
        ctx.addIssue({ code: 'custom', path: ['hours_spent'], message: NEED_HOURS })
      }
      if (requireProject && !data.project_id) {
        ctx.addIssue({ code: 'custom', path: ['project_id'], message: 'Choose a project' })
      }
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
  'task_id',
  'title',
  'description',
  'deviation_reason',
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
  /** New log only: start from this task, date and (actual) hours. */
  prefill?: LogPrefill
  /** New log only: start from an AI draft. */
  draft?: LogDraft
  /** Called after a successful save, before onDone. */
  onSaved?: (log: ProdLog) => void
  /** Called after saving and on cancel. */
  onDone: () => void
}

export interface LogPrefill {
  logDate: string
  task?: Task
}

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

function defaultValues(
  linked: Linked,
  log: ProdLog | null,
  prefill?: LogPrefill,
  draft?: LogDraft,
): LogForm {
  const empty = {
    om_project_id: '',
    title: '',
    description: '',
    deviation_reason: '',
    planned_hours: '',
    is_planned: '' as const,
  }
  if (draft) {
    // The backend only returns active values that fit the linked rules.
    return {
      ...empty,
      log_date: draft.log_date ?? '',
      work_setup_id: asString(draft.work_setup_id) || linked.defaultWorkSetupId,
      planned_hours: asString(draft.planned_hours),
      hours_spent: asString(draft.hours_spent),
      category_id: asString(draft.category_id),
      project_id: asString(draft.project_id),
      activity_id: asString(draft.activity_id),
      om_project_id: asString(draft.om_project_id),
      task_id: asString(draft.task_id),
      title: draft.title ?? '',
      description: draft.description ?? '',
    }
  }
  if (log) {
    return {
      log_date: log.log_date,
      work_setup_id: String(log.work_setup.id),
      planned_hours: asString(log.planned_hours),
      hours_spent: asString(log.hours_spent),
      category_id: String(log.category.id),
      project_id: asString(log.project?.id),
      activity_id: String(log.activity.id),
      om_project_id: asString(log.om_project?.id),
      task_id: asString(log.task_id),
      title: log.title ?? '',
      description: log.description ?? '',
      deviation_reason: log.deviation_reason ?? '',
      is_planned: log.is_planned ? 'planned' : 'unplanned',
    }
  }
  const task = prefill?.task
  // Only active values that fit together can be chosen on a new log.
  const category = task?.category?.is_active ? String(task.category.id) : ''
  const taskProject = task?.project?.is_active ? String(task.project.id) : ''
  return {
    ...empty,
    log_date: prefill?.logDate ?? todayIso(),
    work_setup_id: linked.defaultWorkSetupId,
    hours_spent: '',
    category_id: category,
    project_id: linked.isProjectValid(taskProject, category) ? taskProject : '',
    activity_id: '',
    task_id: task ? String(task.id) : '',
  }
}

const MISSING_HINT: ReactNode = (
  <span className="flex items-center gap-1.5">
    <span className="badge badge-warning badge-sm">Missing</span>
    Not found in your description
  </span>
)

const hasChoice = (choices: Choice[], id: string) => choices.some((c) => String(c.id) === id)

function LogFormInner({
  log,
  isOwn,
  prefill,
  draft,
  onSaved,
  onDone,
  options,
}: LogFormProps & { options: LogOptions }) {
  const toast = useToast()
  const isAdmin = useCurrentUser().data?.role === 'admin'
  const create = useCreateLog()
  const update = useUpdateLog()
  const mutation = log ? update : create
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
    resolver: zodResolver(makeSchema(requireProject)),
    defaultValues: defaultValues(linked, log, prefill, draft),
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

  /** Copy the task's project and category (active ones only: others can't be chosen). */
  function prefillFrom(task: Task) {
    const opts = { shouldDirty: true, shouldValidate: Boolean(errors.category_id) }
    if (task.category?.is_active) setValue('category_id', String(task.category.id), opts)
    if (task.project?.is_active) setValue('project_id', String(task.project.id), opts)
    cascade(getValues('category_id'), getValues('project_id'))
  }

  const category = values.category_id ?? ''
  const project = values.project_id ?? ''
  const projects = projectChoices(category)
  const activities = activityChoices(project)
  const omProjects = omChoices(category)
  const workSetups = withCurrent(options.work_setups, log?.work_setup)
  const categories = withCurrent(options.categories, log?.category)

  // ------------------------------------------------------------ planning lock

  const logDate = values.log_date ?? ''
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
  const showDeviation = deviates || Boolean(values.deviation_reason?.trim())

  // ------------------------------------------------------------ AI draft hints

  /** Highlight for a required field the AI draft left empty, until it is filled in. */
  function missing(field: LogDraftField, kind: 'input' | 'select') {
    if (!draft?.missing_fields.includes(field)) return {}
    if (field === 'hours') {
      if (planned || actual || errors.hours_spent) return {}
    } else if (values[field]?.trim() || errors[field]) {
      return {}
    }
    return { hint: MISSING_HINT, className: `${kind}-warning` }
  }

  // ------------------------------------------------------------ submit

  function onSubmit(data: LogForm) {
    const body = {
      log_date: data.log_date,
      work_setup_id: Number(data.work_setup_id),
      planned_hours: hoursOrNull(data.planned_hours),
      hours_spent: hoursOrNull(data.hours_spent),
      category_id: Number(data.category_id),
      activity_id: Number(data.activity_id),
      om_project_id: omProjects.length ? idOrNull(data.om_project_id) : null,
      title: data.title || null,
      description: data.description || null,
      deviation_reason: showDeviation ? data.deviation_reason || null : null,
      // An old row without a project keeps it empty unless one is chosen.
      ...(data.project_id || !log ? { project_id: idOrNull(data.project_id) } : {}),
      ...(isOwn ? { task_id: idOrNull(data.task_id) } : {}),
      ...(isAdmin && data.is_planned ? { is_planned: data.is_planned === 'planned' } : {}),
    }
    const options = {
      onSuccess: (saved: ProdLog) => {
        onSaved?.(saved)
        toast.success(log ? `Saved “${saved.activity.label}”` : `Added “${saved.activity.label}”`)
        onDone()
      },
      onError: (error: unknown) => {
        if (!applyFieldErrors(error, setError, FIELDS)) toast.error(errorMessage(error))
      },
    }
    if (log) update.mutate({ id: log.id, ...body }, options)
    else create.mutate(body, options)
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
      {draft && (
        <div role="status" className="alert alert-info mb-2 text-sm">
          <SparklesIcon className="size-4" />
          <span>Drafted by AI. Check every field before saving.</span>
        </div>
      )}
      <div className="grid grid-cols-1 gap-x-3 md:grid-cols-2">
        <InputField
          label="Date"
          type="date"
          error={errors.log_date?.message}
          {...missing('log_date', 'input')}
          {...register('log_date')}
        />
        <ChoiceSelect
          label="Work set-up"
          choices={workSetups}
          emptyLabel={workSetups.length ? undefined : 'No work set-ups yet'}
          error={errors.work_setup_id?.message}
          {...missing('work_setup_id', 'select')}
          {...register('work_setup_id')}
        />
        <InputField
          label="Planned hours"
          type="number"
          inputMode="decimal"
          step="0.25"
          min="0.25"
          max="24"
          readOnly={plannedLocked}
          className={plannedLocked ? 'bg-base-200' : ''}
          error={errors.planned_hours?.message}
          {...missing('hours', 'input')}
          {...(lockHint ? { hint: lockHint } : {})}
          {...register('planned_hours')}
        />
        <InputField
          label="Actual hours"
          type="number"
          inputMode="decimal"
          step="0.25"
          min="0.25"
          max="24"
          error={errors.hours_spent?.message}
          {...missing('hours', 'input')}
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
      {isOwn ? (
        <TaskSelect
          label="Task (optional)"
          current={
            log?.task ?? (prefill?.task ? { id: prefill.task.id, title: prefill.task.title } : null)
          }
          error={errors.task_id?.message}
          {...register('task_id')}
          onTaskChosen={prefillFrom}
        />
      ) : (
        log?.task_id && (
          <p className="mt-2 text-sm text-base-content/80">
            Linked to one of {log.user.username}’s tasks (only they can change the link).
          </p>
        )
      )}
      <InputField
        label="Note (optional)"
        autoComplete="off"
        error={errors.title?.message}
        {...register('title')}
      />
      <TextareaField
        label="Remarks (optional)"
        rows={2}
        error={errors.description?.message}
        {...register('description')}
      />
      {isAdmin && (
        <SelectField
          label="Planned / Unplanned (admin)"
          error={errors.is_planned?.message}
          hint="Normally set from the planning deadline when the row is created."
          {...register('is_planned')}
        >
          {!log && <option value="">Automatic</option>}
          <option value="planned">Planned</option>
          <option value="unplanned">Unplanned</option>
        </SelectField>
      )}
      {showDeviation && (
        <TextareaField
          label="Reason for deviation (optional)"
          rows={2}
          hint={deviates ? 'Actual hours differ from planned.' : undefined}
          error={errors.deviation_reason?.message}
          {...register('deviation_reason')}
        />
      )}
      <div className="modal-action">
        <button type="button" className="btn btn-ghost" onClick={onDone}>
          Cancel
        </button>
        <SubmitButton isPending={mutation.isPending}>{log ? 'Save' : 'Add log'}</SubmitButton>
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

type TaskSelectProps = Omit<ComponentProps<typeof SelectField>, 'children'> & {
  /** The task already linked (it may be completed, so not in the open list). */
  current: { id: number; title: string } | null
  onTaskChosen: (task: Task) => void
}

/** The user's open tasks, plus the currently linked task. */
function TaskSelect({
  current,
  onTaskChosen,
  onChange,
  disabled,
  error,
  ...props
}: TaskSelectProps) {
  const tasks = useTaskOptions()
  const open = tasks.data ?? []
  const options = open.map((task) => ({ id: task.id, title: task.title }))
  if (current && !open.some((task) => task.id === current.id)) options.unshift(current)

  return (
    <SelectField
      // Remount once options arrive so React Hook Form re-applies the field value.
      key={tasks.isPending ? 'loading' : 'ready'}
      disabled={disabled || tasks.isPending}
      error={error ?? (tasks.error ? 'Could not load your tasks' : undefined)}
      hint="Choosing a task fills in its project and category."
      onChange={(event) => {
        void onChange?.(event)
        const task = open.find((t) => t.id === Number(event.target.value))
        if (task) onTaskChosen(task)
      }}
      {...props}
    >
      {tasks.isPending ? (
        <option value="">Loading…</option>
      ) : (
        <>
          <option value="">No task</option>
          {options.map((task) => (
            <option key={task.id} value={task.id}>
              {task.title}
            </option>
          ))}
        </>
      )}
    </SelectField>
  )
}
