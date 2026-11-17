/*
 * Create / edit form for a prod log, rendered inside a Modal.
 *
 * Choosing a task pre-fills the project and category from it (both stay editable).
 * A new log can also start from a task (`prefill`, e.g. "Log work" on the daily plan)
 * or from an AI draft (`draft`): required fields the AI left empty are highlighted
 * until filled in.
 * Only the author can link a task: tasks are private, so an admin editing someone
 * else's log keeps the existing link and does not see the task list.
 */
import { zodResolver } from '@hookform/resolvers/zod'
import type { ComponentProps, ReactNode } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import type { LogDraft, LogDraftField } from '../../api/ai'
import { errorMessage } from '../../api/client'
import { useCreateLog, useUpdateLog, type ProdLog } from '../../api/logs'
import { useTaskOptions, type Task } from '../../api/tasks'
import { SparklesIcon } from '../../components/icons'
import { InputField, SelectField, SubmitButton, TextareaField } from '../../components/FormField'
import LookupSelect from '../../components/LookupSelect'
import { useToast } from '../../components/toast-context'
import { todayIso } from '../../lib/format'
import { applyFieldErrors } from '../../lib/forms'

const HOURS_PATTERN = /^\d{1,2}(\.\d{1,2})?$/
const HOURS_MESSAGE = 'Enter between 0.01 and 24 hours (up to 2 decimals)'

// Mirrors app/schemas/prod_logs.py. Select values are id strings ("" = none).
const logSchema = z.object({
  log_date: z.string().min(1, 'Choose a date'),
  title: z.string().trim().min(1, 'Enter a title').max(200, 'Use at most 200 characters'),
  hours_spent: z
    .string()
    .trim()
    .refine((v) => HOURS_PATTERN.test(v) && Number(v) > 0 && Number(v) <= 24, HOURS_MESSAGE),
  task_id: z.string(),
  project_id: z.string(),
  category_id: z.string().min(1, 'Choose a category'),
  description: z.string().trim().max(10000, 'Use at most 10000 characters'),
})
type LogForm = z.infer<typeof logSchema>

const FIELDS = [
  'log_date',
  'title',
  'hours_spent',
  'task_id',
  'project_id',
  'category_id',
  'description',
] as const

const idOrNull = (value: string) => (value ? Number(value) : null)

interface LogFormProps {
  /** null = new log (always the caller's own). */
  log: ProdLog | null
  /** False when an admin edits someone else's log. */
  isOwn: boolean
  /** New log only: start from this task, date and hours. */
  prefill?: LogPrefill
  /** New log only: start from an AI draft. */
  draft?: LogDraft
  /** Called after a successful save, before onDone. */
  onSaved?: (log: ProdLog) => void
  /** Called after saving and on cancel. */
  onDone: () => void
}

export interface LogPrefill {
  task: Task
  logDate: string
  hours?: number | null
}

const asString = (value: number | string | null) => (value === null ? '' : String(value))

function defaultValues(log: ProdLog | null, prefill?: LogPrefill, draft?: LogDraft): LogForm {
  if (draft) {
    // The backend only returns active values the user may choose.
    return {
      log_date: draft.log_date ?? '',
      title: draft.title ?? '',
      hours_spent: asString(draft.hours_spent),
      task_id: asString(draft.task_id),
      project_id: asString(draft.project_id),
      category_id: asString(draft.category_id),
      description: draft.description ?? '',
    }
  }
  if (log) {
    return {
      log_date: log.log_date,
      title: log.title,
      hours_spent: String(log.hours_spent),
      task_id: log.task_id ? String(log.task_id) : '',
      project_id: log.project ? String(log.project.id) : '',
      category_id: String(log.category.id),
      description: log.description ?? '',
    }
  }
  const task = prefill?.task
  // Only active values can be chosen on a new log.
  const project = task?.project?.is_active ? String(task.project.id) : ''
  const category = task?.category?.is_active ? String(task.category.id) : ''
  return {
    log_date: prefill?.logDate ?? todayIso(),
    title: task?.title ?? '',
    hours_spent: prefill?.hours ? String(prefill.hours) : '',
    task_id: task ? String(task.id) : '',
    project_id: project,
    category_id: category,
    description: '',
  }
}

const MISSING_HINT: ReactNode = (
  <span className="flex items-center gap-1.5">
    <span className="badge badge-warning badge-sm">Missing</span>
    Not found in your description
  </span>
)

export default function LogFormBody({ log, isOwn, prefill, draft, onSaved, onDone }: LogFormProps) {
  const toast = useToast()
  const create = useCreateLog()
  const update = useUpdateLog()
  const mutation = log ? update : create
  const {
    register,
    handleSubmit,
    setError,
    setValue,
    control,
    formState: { errors },
  } = useForm<LogForm>({
    resolver: zodResolver(logSchema),
    defaultValues: defaultValues(log, prefill, draft),
  })

  /** Highlight for a required field the AI draft left empty, until it is filled in. */
  const values = useWatch({ control })
  function missing(field: LogDraftField, kind: 'input' | 'select') {
    if (!draft?.missing_fields.includes(field) || values[field]?.trim() || errors[field]) {
      return {}
    }
    return { hint: MISSING_HINT, className: `${kind}-warning` }
  }

  /** Copy the task's project and category (active ones only: others can't be chosen). */
  function prefillFrom(task: Task) {
    const opts = { shouldDirty: true, shouldValidate: Boolean(errors.category_id) }
    if (task.project?.is_active) setValue('project_id', String(task.project.id), opts)
    if (task.category?.is_active) setValue('category_id', String(task.category.id), opts)
  }

  function onSubmit(data: LogForm) {
    const body = {
      log_date: data.log_date,
      title: data.title,
      hours_spent: Number(data.hours_spent),
      project_id: idOrNull(data.project_id),
      category_id: Number(data.category_id),
      description: data.description || null,
      ...(isOwn ? { task_id: idOrNull(data.task_id) } : {}),
    }
    const options = {
      onSuccess: (saved: ProdLog) => {
        onSaved?.(saved)
        toast.success(log ? `Saved “${saved.title}”` : `Logged ${saved.hours_spent} h`)
        onDone()
      },
      onError: (error: unknown) => {
        if (!applyFieldErrors(error, setError, FIELDS)) toast.error(errorMessage(error))
      },
    }
    if (log) update.mutate({ id: log.id, ...body }, options)
    else create.mutate(body, options)
  }

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
        <InputField
          label="Hours"
          type="number"
          inputMode="decimal"
          step="0.25"
          min="0.25"
          max="24"
          error={errors.hours_spent?.message}
          {...missing('hours_spent', 'input')}
          {...register('hours_spent')}
        />
      </div>
      <InputField
        label="Title"
        autoFocus={!log && !prefill && !draft}
        autoComplete="off"
        error={errors.title?.message}
        {...missing('title', 'input')}
        {...register('title')}
      />
      {isOwn ? (
        <TaskSelect
          label="Task (optional)"
          current={
            log?.task ?? (prefill ? { id: prefill.task.id, title: prefill.task.title } : null)
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
      <div className="grid grid-cols-1 gap-x-3 md:grid-cols-2">
        <LookupSelect
          kind="projects"
          label="Project"
          current={log?.project}
          emptyLabel="No project"
          error={errors.project_id?.message}
          {...register('project_id')}
        />
        <LookupSelect
          kind="categories"
          label="Category"
          current={log?.category}
          emptyLabel="Choose a category"
          error={errors.category_id?.message}
          {...missing('category_id', 'select')}
          {...register('category_id')}
        />
      </div>
      <TextareaField
        label="Description (optional)"
        rows={3}
        error={errors.description?.message}
        {...register('description')}
      />
      <div className="modal-action">
        <button type="button" className="btn btn-ghost" onClick={onDone}>
          Cancel
        </button>
        <SubmitButton isPending={mutation.isPending}>{log ? 'Save' : 'Add log'}</SubmitButton>
      </div>
    </form>
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
