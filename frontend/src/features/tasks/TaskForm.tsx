/*
 * Create / edit form for a task, rendered inside a Modal.
 *
 * New tasks start with the default status and priority (found by `is_default`, never by
 * label). When editing, a value that has since been deactivated stays selectable for
 * this task (LookupSelect `current`) but cannot be chosen for another.
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'

import { errorMessage } from '../../api/client'
import { useLookups } from '../../api/lookups'
import { useCreateTask, useUpdateTask, type Task } from '../../api/tasks'
import AsyncState from '../../components/AsyncState'
import { DateField } from '../../components/DateInput'
import { InputField, SubmitButton, TextareaField } from '../../components/FormField'
import LookupSelect from '../../components/LookupSelect'
import { SkeletonForm } from '../../components/Skeleton'
import { useToast } from '../../components/toast-context'
import { applyFieldErrors } from '../../lib/forms'

// Mirrors app/schemas/tasks.py. Select values are id strings ("" = none).
const taskSchema = z.object({
  title: z.string().trim().min(1, 'Enter a title').max(200, 'Use at most 200 characters'),
  description: z.string().trim().max(10000, 'Use at most 10000 characters'),
  status_id: z.string().min(1, 'Choose a status'),
  priority_id: z.string().min(1, 'Choose a priority'),
  project_id: z.string(),
  category_id: z.string(),
  due_date: z.string(),
})
type TaskForm = z.infer<typeof taskSchema>

const FIELDS = [
  'title',
  'description',
  'status_id',
  'priority_id',
  'project_id',
  'category_id',
  'due_date',
] as const

const idOrNull = (value: string) => (value ? Number(value) : null)

interface TaskFormProps {
  /** null = new task. */
  task: Task | null
  onDone: () => void
}

export default function TaskFormBody({ task, onDone }: TaskFormProps) {
  const statuses = useLookups('statuses')
  const priorities = useLookups('priorities')

  // Wait for the values so a new task can start on the defaults.
  return (
    <AsyncState
      query={{
        isPending: statuses.isPending || priorities.isPending,
        error: statuses.error ?? priorities.error,
        refetch: () => {
          void statuses.refetch()
          void priorities.refetch()
        },
      }}
      skeleton={<SkeletonForm fields={5} />}
    >
      {() => (
        <TaskFormFields
          task={task}
          defaultStatusId={statuses.data?.find((s) => s.is_default)?.id}
          defaultPriorityId={priorities.data?.find((p) => p.is_default)?.id}
          onDone={onDone}
        />
      )}
    </AsyncState>
  )
}

function TaskFormFields({
  task,
  defaultStatusId,
  defaultPriorityId,
  onDone,
}: TaskFormProps & { defaultStatusId?: number; defaultPriorityId?: number }) {
  const toast = useToast()
  const create = useCreateTask()
  const update = useUpdateTask()
  const mutation = task ? update : create
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors },
  } = useForm<TaskForm>({
    resolver: zodResolver(taskSchema),
    defaultValues: {
      title: task?.title ?? '',
      description: task?.description ?? '',
      status_id: String(task?.status.id ?? defaultStatusId ?? ''),
      priority_id: String(task?.priority.id ?? defaultPriorityId ?? ''),
      project_id: task?.project ? String(task.project.id) : '',
      category_id: task?.category ? String(task.category.id) : '',
      due_date: task?.due_date ?? '',
    },
  })

  function onSubmit(data: TaskForm) {
    const body = {
      title: data.title,
      description: data.description || null,
      status_id: Number(data.status_id),
      priority_id: Number(data.priority_id),
      project_id: idOrNull(data.project_id),
      category_id: idOrNull(data.category_id),
      due_date: data.due_date || null,
    }
    const options = {
      onSuccess: (saved: Task) => {
        toast.success(task ? `Saved “${saved.title}”` : `Task “${saved.title}” created`)
        onDone()
      },
      onError: (error: unknown) => {
        if (!applyFieldErrors(error, setError, FIELDS)) toast.error(errorMessage(error))
      },
    }
    if (task) update.mutate({ id: task.id, ...body }, options)
    else create.mutate(body, options)
  }

  return (
    <form onSubmit={(e) => void handleSubmit(onSubmit)(e)} noValidate>
      <InputField
        label="Title"
        autoFocus
        autoComplete="off"
        error={errors.title?.message}
        {...register('title')}
      />
      <TextareaField
        label="Description (optional)"
        rows={3}
        error={errors.description?.message}
        {...register('description')}
      />
      <div className="grid grid-cols-1 gap-x-3 md:grid-cols-2">
        <LookupSelect
          kind="statuses"
          label="Status"
          current={task?.status}
          error={errors.status_id?.message}
          {...register('status_id')}
        />
        <LookupSelect
          kind="priorities"
          label="Priority"
          current={task?.priority}
          error={errors.priority_id?.message}
          {...register('priority_id')}
        />
        <LookupSelect
          kind="projects"
          label="Project"
          current={task?.project}
          emptyLabel="No project"
          error={errors.project_id?.message}
          {...register('project_id')}
        />
        <LookupSelect
          kind="categories"
          label="Category"
          current={task?.category}
          emptyLabel="No category"
          error={errors.category_id?.message}
          {...register('category_id')}
        />
        <Controller
          control={control}
          name="due_date"
          render={({ field }) => (
            <DateField
              label="Due date (optional)"
              placeholder="No due date"
              clearable
              error={errors.due_date?.message}
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
              ref={field.ref}
            />
          )}
        />
      </div>
      <div className="modal-action">
        <button type="button" className="btn btn-ghost" onClick={onDone}>
          Cancel
        </button>
        <SubmitButton isPending={mutation.isPending}>{task ? 'Save' : 'Create task'}</SubmitButton>
      </div>
    </form>
  )
}
