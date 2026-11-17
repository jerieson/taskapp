/*
 * Create / edit form for a process with an ordered step editor, rendered in a Modal.
 *
 * Editing saves the name/description and then the complete step list (PUT
 * /processes/{id}/steps): kept steps are updated, new ones added, removed ones
 * deleted. Runs already started keep their tasks either way.
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useFieldArray, useForm, type Path, type UseFormSetError } from 'react-hook-form'
import { z } from 'zod'

import { ApiError, errorMessage } from '../../api/client'
import {
  useCreateProcess,
  useEditProcess,
  useProcess,
  type Process,
  type ProcessStep,
} from '../../api/processes'
import AsyncState from '../../components/AsyncState'
import { InputField, SubmitButton, TextareaField } from '../../components/FormField'
import { ArrowDownIcon, ArrowUpIcon, PlusIcon, TrashIcon } from '../../components/icons'
import LookupSelect from '../../components/LookupSelect'
import { SkeletonForm } from '../../components/Skeleton'
import { useToast } from '../../components/toast-context'

const MAX_STEPS = 100
const HOURS_PATTERN = /^\d{1,2}(\.\d{1,2})?$/

// Mirrors app/schemas/processes.py. Select values are id strings ("" = none).
const stepSchema = z.object({
  /** The saved step's id; null for a step added in this form. */
  stepId: z.number().nullable(),
  title: z.string().trim().min(1, 'Enter a title').max(200, 'Use at most 200 characters'),
  description: z.string().trim().max(10000, 'Use at most 10000 characters'),
  default_category_id: z.string(),
  estimated_hours: z
    .string()
    .trim()
    .refine(
      (v) => v === '' || (HOURS_PATTERN.test(v) && Number(v) > 0 && Number(v) <= 24),
      'Enter hours from 0.01 to 24',
    ),
})

const processSchema = z.object({
  name: z.string().trim().min(1, 'Enter a name').max(100, 'Use at most 100 characters'),
  description: z.string().trim().max(10000, 'Use at most 10000 characters'),
  steps: z.array(stepSchema).max(MAX_STEPS, `Use at most ${MAX_STEPS} steps`),
})
type ProcessForm = z.infer<typeof processSchema>
type StepForm = z.infer<typeof stepSchema>

const STEP_FIELD = /^steps\.\d+\.(title|description|default_category_id|estimated_hours)$/

/** Copy API field errors (including `steps.N.field`) onto the form. */
function applyServerErrors(error: unknown, setError: UseFormSetError<ProcessForm>): boolean {
  if (!(error instanceof ApiError)) return false
  let matched = false
  for (const [field, message] of Object.entries(error.fields)) {
    if (field === 'name' || field === 'description' || STEP_FIELD.test(field)) {
      setError(field as Path<ProcessForm>, { type: 'server', message })
      matched = true
    }
  }
  return matched
}

const emptyStep = (): StepForm => ({
  stepId: null,
  title: '',
  description: '',
  default_category_id: '',
  estimated_hours: '',
})

const stepToForm = (step: ProcessStep): StepForm => ({
  stepId: step.id,
  title: step.title,
  description: step.description ?? '',
  default_category_id: step.default_category ? String(step.default_category.id) : '',
  estimated_hours: step.estimated_hours === null ? '' : String(step.estimated_hours),
})

const stepToApi = (step: StepForm) => ({
  title: step.title,
  description: step.description || null,
  default_category_id: step.default_category_id ? Number(step.default_category_id) : null,
  estimated_hours: step.estimated_hours ? Number(step.estimated_hours) : null,
})

interface ProcessFormProps {
  /** null = new process. */
  processId: number | null
  onDone: (saved: Process) => void
  onCancel: () => void
}

export default function ProcessFormBody({ processId, onDone, onCancel }: ProcessFormProps) {
  if (processId === null)
    return <ProcessFields process={null} onDone={onDone} onCancel={onCancel} />
  return <EditProcess processId={processId} onDone={onDone} onCancel={onCancel} />
}

function EditProcess({ processId, onDone, onCancel }: ProcessFormProps & { processId: number }) {
  const process = useProcess(processId)
  return (
    <AsyncState query={process} skeleton={<SkeletonForm fields={4} />}>
      {() =>
        process.data && <ProcessFields process={process.data} onDone={onDone} onCancel={onCancel} />
      }
    </AsyncState>
  )
}

function ProcessFields({
  process,
  onDone,
  onCancel,
}: Omit<ProcessFormProps, 'processId'> & { process: Process | null }) {
  const toast = useToast()
  const create = useCreateProcess()
  const edit = useEditProcess()
  const mutation = process ? edit : create
  const savedSteps = new Map(process?.steps.map((step) => [step.id, step]))

  const {
    register,
    control,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<ProcessForm>({
    resolver: zodResolver(processSchema),
    defaultValues: {
      name: process?.name ?? '',
      description: process?.description ?? '',
      steps: process ? process.steps.map(stepToForm) : [emptyStep()],
    },
  })
  const steps = useFieldArray({ control, name: 'steps' })

  function onSubmit(data: ProcessForm) {
    const options = {
      onSuccess: (saved: Process) => {
        toast.success(process ? `Saved “${saved.name}”` : `Process “${saved.name}” created`)
        onDone(saved)
      },
      onError: (error: unknown) => {
        if (!applyServerErrors(error, setError)) toast.error(errorMessage(error))
      },
    }
    const fields = { name: data.name, description: data.description || null }
    if (process) {
      edit.mutate(
        {
          id: process.id,
          ...fields,
          steps: data.steps.map((step) => ({ id: step.stepId, ...stepToApi(step) })),
        },
        options,
      )
    } else {
      create.mutate({ ...fields, steps: data.steps.map(stepToApi) }, options)
    }
  }

  return (
    <form onSubmit={(e) => void handleSubmit(onSubmit)(e)} noValidate>
      <InputField
        label="Name"
        autoFocus
        autoComplete="off"
        error={errors.name?.message}
        {...register('name')}
      />
      <TextareaField
        label="Description (optional)"
        rows={2}
        error={errors.description?.message}
        {...register('description')}
      />

      <fieldset className="mt-4">
        <legend className="font-semibold">Steps</legend>
        <p className="mt-1 text-sm text-base-content/80">
          Each step becomes a task when you start a run.
          {process && ' Changes apply to new runs only; runs already started keep their tasks.'}
        </p>
        {(errors.steps?.message ?? errors.steps?.root?.message) && (
          <p className="mt-2 text-sm">{errors.steps.message ?? errors.steps.root?.message}</p>
        )}

        {steps.fields.length === 0 ? (
          <p className="mt-3 rounded-box border border-dashed border-base-300 p-4 text-center text-sm text-base-content/80">
            No steps yet. A process needs at least one step to start a run.
          </p>
        ) : (
          <ol className="mt-3 flex flex-col gap-3">
            {steps.fields.map((field, index) => {
              const stepErrors = errors.steps?.[index]
              const saved = field.stepId !== null ? savedSteps.get(field.stepId) : undefined
              const n = index + 1
              return (
                <li key={field.id} className="rounded-box border border-base-300 bg-base-200 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold">Step {n}</span>
                    <div className="flex items-center gap-1">
                      <div className="join">
                        <button
                          type="button"
                          className="btn join-item btn-sm btn-square"
                          onClick={() => steps.move(index, index - 1)}
                          disabled={index === 0}
                          aria-label={`Move step ${n} up`}
                        >
                          <ArrowUpIcon className="size-4" />
                        </button>
                        <button
                          type="button"
                          className="btn join-item btn-sm btn-square"
                          onClick={() => steps.move(index, index + 1)}
                          disabled={index === steps.fields.length - 1}
                          aria-label={`Move step ${n} down`}
                        >
                          <ArrowDownIcon className="size-4" />
                        </button>
                      </div>
                      <button
                        type="button"
                        className="btn btn-sm btn-ghost btn-square"
                        onClick={() => steps.remove(index)}
                        aria-label={`Remove step ${n}`}
                        title="Remove step"
                      >
                        <TrashIcon className="size-4" />
                      </button>
                    </div>
                  </div>
                  <InputField
                    label="Title"
                    autoComplete="off"
                    error={stepErrors?.title?.message}
                    {...register(`steps.${index}.title`)}
                  />
                  <div className="grid grid-cols-1 gap-x-3 md:grid-cols-2">
                    <LookupSelect
                      kind="categories"
                      label="Default category"
                      current={saved?.default_category}
                      emptyLabel="No category"
                      error={stepErrors?.default_category_id?.message}
                      {...register(`steps.${index}.default_category_id`)}
                    />
                    <InputField
                      label="Estimated hours (optional)"
                      inputMode="decimal"
                      autoComplete="off"
                      placeholder="e.g. 1.5"
                      error={stepErrors?.estimated_hours?.message}
                      {...register(`steps.${index}.estimated_hours`)}
                    />
                  </div>
                  <TextareaField
                    label="Description (optional)"
                    rows={2}
                    error={stepErrors?.description?.message}
                    {...register(`steps.${index}.description`)}
                  />
                </li>
              )
            })}
          </ol>
        )}
        <button
          type="button"
          className="btn btn-sm mt-3"
          onClick={() => steps.append(emptyStep())}
          disabled={steps.fields.length >= MAX_STEPS}
        >
          <PlusIcon className="size-4" />
          Add step
        </button>
      </fieldset>

      <div className="modal-action">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
        <SubmitButton isPending={mutation.isPending}>
          {process ? 'Save' : 'Create process'}
        </SubmitButton>
      </div>
    </form>
  )
}
