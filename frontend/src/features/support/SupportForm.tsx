/*
 * Create / edit form for a support entry, shown in a modal. Project, module and
 * sub-module are free text with suggestions from the values already in use.
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useId } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { errorMessage } from '../../api/client'
import {
  useCreateSupportEntry,
  useSupportFacets,
  useUpdateSupportEntry,
  type SupportEntry,
} from '../../api/support'
import { InputField, SubmitButton, TextareaField } from '../../components/FormField'
import LookupSelect from '../../components/LookupSelect'
import Modal from '../../components/Modal'
import { useToast } from '../../components/toast-context'
import { applyFieldErrors } from '../../lib/forms'

const place = z.string().trim().max(100, 'Use at most 100 characters')
const longText = z.string().trim().max(10000, 'Use at most 10,000 characters')

const schema = z.object({
  type_id: z.string().min(1, 'Choose a type'),
  project: place,
  module: place,
  sub_module: place,
  concern: z
    .string()
    .trim()
    .min(1, 'Describe the concern')
    .max(2000, 'Use at most 2,000 characters'),
  cause: longText,
  resolution: longText,
  query: z.string().max(20000, 'Use at most 20,000 characters'),
  notes: longText,
})

type FormValues = z.input<typeof schema>
type Parsed = z.output<typeof schema>

const FIELDS = [
  'type_id',
  'project',
  'module',
  'sub_module',
  'concern',
  'cause',
  'resolution',
  'query',
  'notes',
] as const

function defaults(entry?: SupportEntry): FormValues {
  return {
    type_id: entry ? String(entry.type.id) : '',
    project: entry?.project ?? '',
    module: entry?.module ?? '',
    sub_module: entry?.sub_module ?? '',
    concern: entry?.concern ?? '',
    cause: entry?.cause ?? '',
    resolution: entry?.resolution ?? '',
    query: entry?.query ?? '',
    notes: entry?.notes ?? '',
  }
}

/** Blank optional fields are sent as null (which also clears them on edit). */
function toBody(values: Parsed) {
  const orNull = (value: string) => (value.trim() ? value : null)
  return {
    type_id: Number(values.type_id),
    project: orNull(values.project),
    module: orNull(values.module),
    sub_module: orNull(values.sub_module),
    concern: values.concern,
    cause: orNull(values.cause),
    resolution: orNull(values.resolution),
    query: orNull(values.query),
    notes: orNull(values.notes),
  }
}

function Suggestions({ id, values }: { id: string; values: string[] | undefined }) {
  return (
    <datalist id={id}>
      {values?.map((value) => (
        <option key={value} value={value} />
      ))}
    </datalist>
  )
}

function SupportFormBody({
  entry,
  onCancel,
  onSaved,
}: {
  entry?: SupportEntry
  onCancel: () => void
  onSaved: (entry: SupportEntry) => void
}) {
  const toast = useToast()
  const create = useCreateSupportEntry()
  const update = useUpdateSupportEntry()
  const facets = useSupportFacets()
  const listId = useId()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<FormValues, unknown, Parsed>({
    resolver: zodResolver(schema),
    defaultValues: defaults(entry),
  })
  const formError = errors.root?.message
  const isPending = create.isPending || update.isPending

  function submit(values: Parsed) {
    const body = toBody(values)
    const options = {
      onSuccess: (saved: SupportEntry) => {
        toast.success(entry ? 'Entry saved' : 'Entry added')
        onSaved(saved)
      },
      onError: (error: unknown) => {
        if (!applyFieldErrors(error, setError, FIELDS)) {
          setError('root', { message: errorMessage(error) })
        }
      },
    }
    if (entry) update.mutate({ id: entry.id, ...body }, options)
    else create.mutate(body, options)
  }

  return (
    <form onSubmit={(e) => void handleSubmit(submit)(e)} noValidate>
      {formError && (
        <div role="alert" className="alert alert-error mb-3 text-sm">
          {formError}
        </div>
      )}
      <div className="grid grid-cols-1 gap-x-3 md:grid-cols-2">
        <LookupSelect
          kind="support-types"
          label="Type"
          current={entry?.type}
          emptyLabel="Choose a type"
          error={errors.type_id?.message}
          {...register('type_id')}
        />
        <InputField
          label="Project (optional)"
          list={`${listId}-projects`}
          autoComplete="off"
          error={errors.project?.message}
          {...register('project')}
        />
        <InputField
          label="Module (optional)"
          list={`${listId}-modules`}
          autoComplete="off"
          error={errors.module?.message}
          {...register('module')}
        />
        <InputField
          label="Sub-module (optional)"
          list={`${listId}-sub-modules`}
          autoComplete="off"
          error={errors.sub_module?.message}
          {...register('sub_module')}
        />
      </div>
      <Suggestions id={`${listId}-projects`} values={facets.data?.projects} />
      <Suggestions id={`${listId}-modules`} values={facets.data?.modules} />
      <Suggestions id={`${listId}-sub-modules`} values={facets.data?.sub_modules} />

      <TextareaField
        label="Concern"
        rows={2}
        error={errors.concern?.message}
        {...register('concern')}
      />
      <TextareaField
        label="Cause (optional)"
        rows={3}
        error={errors.cause?.message}
        {...register('cause')}
      />
      <TextareaField
        label="Resolution (optional)"
        rows={4}
        error={errors.resolution?.message}
        {...register('resolution')}
      />
      <TextareaField
        label="Query (optional)"
        rows={6}
        spellCheck={false}
        className="font-mono text-sm"
        hint="SQL is shown as code with a Copy button."
        error={errors.query?.message}
        {...register('query')}
      />
      <TextareaField
        label="Notes (optional)"
        rows={2}
        error={errors.notes?.message}
        {...register('notes')}
      />

      <div className="modal-action">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={isPending}>
          Cancel
        </button>
        <SubmitButton isPending={isPending}>{entry ? 'Save' : 'Add entry'}</SubmitButton>
      </div>
    </form>
  )
}

/** null = closed; 'new' = create; an entry = edit it. */
export type SupportFormState = 'new' | SupportEntry | null

export default function SupportFormModal({
  state,
  onClose,
  onSaved,
}: {
  state: SupportFormState
  onClose: () => void
  onSaved?: (entry: SupportEntry, created: boolean) => void
}) {
  const entry = state && state !== 'new' ? state : undefined
  return (
    <Modal open={state !== null} title={entry ? 'Edit entry' : 'New entry'} onClose={onClose} wide>
      {state !== null && (
        <SupportFormBody
          entry={entry}
          onCancel={onClose}
          onSaved={(saved) => {
            onClose()
            onSaved?.(saved, !entry)
          }}
        />
      )}
    </Modal>
  )
}
