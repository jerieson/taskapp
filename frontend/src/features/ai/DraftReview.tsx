/*
 * Review of a multi-row AI draft: one card per row (date, values, hours), with fields
 * the AI could not fill flagged. "Edit" opens the normal log form inside the card (it
 * hands the checked values back instead of saving), "Remove" drops the row, and
 * "Save N rows" creates them all at once through the bulk endpoint (all or none). A
 * save error keyed `rows.N.field` is shown on that row's card.
 *
 * After a row is edited, the review offers to fill the same category, project and
 * activity into other rows that lack them (a range often needs the same fix on every
 * day), but only where the value fits the row's other values.
 */
import { useMemo, useState } from 'react'

import type { LogDraftField, LogDraftRow } from '../../api/ai'
import { ApiError, errorMessage } from '../../api/client'
import { useCreateLogs, type ProdLogCreate } from '../../api/logs'
import { useLogOptions, type LogOptions } from '../../api/lookups'
import ErrorAlert from '../../components/ErrorAlert'
import { PencilIcon, SparklesIcon, TrashIcon } from '../../components/icons'
import { SkeletonForm } from '../../components/Skeleton'
import { useToast } from '../../components/toast-context'
import { formatDayWithWeekday, formatHours } from '../../lib/format'
import LogFormBody, { type DraftValues } from '../logs/LogForm'

interface ReviewRow extends DraftValues {
  key: number
}

const FIELD_LABEL: Record<Exclude<LogDraftField, 'hours'>, string> = {
  work_setup_id: 'work set-up',
  category_id: 'category',
  project_id: 'project',
  activity_id: 'activity',
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

/** Required values a row still lacks (it cannot be saved until they are filled in). */
function missingOf(row: DraftValues): string[] {
  const missing = (Object.keys(FIELD_LABEL) as (keyof typeof FIELD_LABEL)[])
    .filter((field) => row[field] === null)
    .map((field) => FIELD_LABEL[field])
  if (row.planned_hours === null && row.hours_spent === null) missing.push('hours')
  return missing
}

/** The AI was unsure whether the hours were per day or per week. */
const checkHours = (row: DraftValues) =>
  row.missing_fields.includes('hours') && (row.planned_hours !== null || row.hours_spent !== null)

function toCreate(row: DraftValues): ProdLogCreate {
  return {
    log_date: row.log_date,
    work_setup_id: row.work_setup_id,
    planned_hours: row.planned_hours,
    hours_spent: row.hours_spent,
    category_id: row.category_id,
    project_id: row.project_id,
    activity_id: row.activity_id ?? 0, // never sent: rows missing it cannot be saved
    om_project_id: row.om_project_id,
    description: row.description,
    deviation_reason_id: row.deviation_reason_id ?? null,
    is_planned: row.is_planned,
  }
}

/**
 * `target` with its empty category, project and activity filled from `source`, where
 * they fit together (category -> project -> activity), or null if nothing can be filled.
 */
function fillFrom(source: DraftValues, target: ReviewRow): ReviewRow | null {
  const next = { ...target }
  if (next.category_id === null && source.category_id !== null) {
    if (next.project_id === null || next.project_id === source.project_id) {
      next.category_id = source.category_id
    }
  }
  if (next.project_id === null && source.project_id !== null) {
    if (next.category_id === source.category_id) next.project_id = source.project_id
  }
  if (next.activity_id === null && source.activity_id !== null) {
    if (next.project_id === source.project_id) next.activity_id = source.activity_id
  }
  const changed =
    next.category_id !== target.category_id ||
    next.project_id !== target.project_id ||
    next.activity_id !== target.activity_id
  return changed ? next : null
}

/** Save errors by row index, from fields keyed "rows.N.field". */
function rowErrors(error: unknown): Map<number, string[]> {
  const byRow = new Map<number, string[]>()
  if (!(error instanceof ApiError)) return byRow
  for (const [key, message] of Object.entries(error.fields)) {
    const match = /^rows\.(\d+)\./.exec(key)
    if (!match) continue
    const index = Number(match[1])
    byRow.set(index, [...(byRow.get(index) ?? []), message])
  }
  return byRow
}

interface DraftReviewProps {
  rows: LogDraftRow[]
  /** Called after the rows were saved, before onDone. */
  onSaved: () => void
  /** Called after saving and on cancel. */
  onDone: () => void
}

export default function DraftReview(props: DraftReviewProps) {
  const options = useLogOptions()
  if (options.isPending) return <SkeletonForm fields={4} />
  if (options.error) {
    return (
      <ErrorAlert
        title="Could not load the form options"
        error={options.error}
        onRetry={() => void options.refetch()}
      />
    )
  }
  return <Review {...props} options={options.data} />
}

function Review({
  rows: initial,
  onSaved,
  onDone,
  options,
}: DraftReviewProps & { options: LogOptions }) {
  const toast = useToast()
  const save = useCreateLogs()
  const [rows, setRows] = useState<ReviewRow[]>(() => initial.map((row, key) => ({ ...row, key })))
  const [editing, setEditing] = useState<number | null>(null)
  /** Save errors by row key (cleared when the row changes). */
  const [errors, setErrors] = useState<Map<number, string[]>>(new Map())
  /** The row just edited, while other rows could take its values. */
  const [fillSource, setFillSource] = useState<ReviewRow | null>(null)
  const fillable = fillSource
    ? rows.flatMap((row) => {
        const filled = fillFrom(fillSource, row)
        return filled ? [filled] : []
      })
    : []

  const incomplete = rows.filter((row) => missingOf(row).length > 0).length
  const canSave = rows.length > 0 && incomplete === 0 && editing === null && !save.isPending

  function update(key: number, values: DraftValues) {
    setRows((current) => current.map((row) => (row.key === key ? { ...values, key } : row)))
    setErrors((current) => new Map([...current].filter(([k]) => k !== key)))
    setFillSource({ ...values, key })
    save.reset()
  }

  function fillOthers() {
    const filled = new Map(fillable.map((row) => [row.key, row]))
    setRows((current) => current.map((row) => filled.get(row.key) ?? row))
    setErrors((current) => new Map([...current].filter(([k]) => !filled.has(k))))
    setFillSource(null)
    toast.success(`Filled in ${plural(filled.size, 'row')}`)
  }

  function remove(key: number) {
    setRows((current) => current.filter((row) => row.key !== key))
    setErrors((current) => new Map([...current].filter(([k]) => k !== key)))
    save.reset()
  }

  function submit() {
    if (!canSave) return
    save.mutate(rows.map(toCreate), {
      onSuccess: (result) => {
        toast.success(`Added ${plural(result.created, 'row')}`)
        onSaved()
        onDone()
      },
      onError: (error) => {
        const byIndex = rowErrors(error)
        setErrors(
          new Map(
            [...byIndex].flatMap(([index, messages]) => {
              const row = rows[index]
              return row ? [[row.key, messages] as const] : []
            }),
          ),
        )
        toast.error(errorMessage(error))
      },
    })
  }

  return (
    <div>
      <div role="status" className="alert alert-info mb-3 text-sm">
        <SparklesIcon className="size-4" />
        <span>
          Drafted by AI: {plural(rows.length, 'row')}. Check each row, edit or remove it, then save
          them all.
        </span>
      </div>

      {rows.length === 0 ? (
        <p className="rounded-box bg-base-200 px-3 py-4 text-center text-sm">
          All rows removed. Close this and describe your work again.
        </p>
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Draft rows">
          {rows.map((row, index) => (
            <li key={row.key}>
              <DraftCard
                row={row}
                index={index}
                options={options}
                editing={editing === row.key}
                busy={editing !== null || save.isPending}
                errors={errors.get(row.key)}
                onEdit={() => {
                  setEditing(row.key)
                  setFillSource(null)
                }}
                onRemove={() => remove(row.key)}
                onApply={(values) => update(row.key, values)}
                onCloseEditor={() => setEditing(null)}
              />
              {fillSource?.key === row.key && fillable.length > 0 && editing === null && (
                <div role="status" className="alert mt-2 flex-wrap text-sm">
                  <span className="flex-1">
                    {plural(fillable.length, 'other row')}{' '}
                    {fillable.length === 1 ? 'lacks' : 'lack'} the category, project or activity you
                    just chose.
                  </span>
                  <div className="flex gap-1">
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setFillSource(null)}
                    >
                      No thanks
                    </button>
                    <button type="button" className="btn btn-primary btn-sm" onClick={fillOthers}>
                      Fill them in
                    </button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {save.isError && errors.size === 0 && (
        <div className="mt-3">
          <ErrorAlert error={save.error} title="Could not save the rows" />
        </div>
      )}

      <div className="modal-action flex-wrap items-center">
        {incomplete > 0 && (
          <p className="mr-auto text-sm text-base-content/80">
            Fill in the missing values on {plural(incomplete, 'row')} to save.
          </p>
        )}
        <button type="button" className="btn btn-ghost" onClick={onDone}>
          Cancel
        </button>
        <button type="button" className="btn btn-primary" disabled={!canSave} onClick={submit}>
          {save.isPending && <span className="loading loading-spinner loading-sm" />}
          Save {plural(rows.length, 'row')}
        </button>
      </div>
    </div>
  )
}

interface DraftCardProps {
  row: ReviewRow
  index: number
  options: LogOptions
  editing: boolean
  /** Another row is being edited, or the rows are being saved. */
  busy: boolean
  errors: string[] | undefined
  onEdit: () => void
  onRemove: () => void
  onApply: (values: DraftValues) => void
  onCloseEditor: () => void
}

function DraftCard({
  row,
  index,
  options,
  editing,
  busy,
  errors,
  onEdit,
  onRemove,
  onApply,
  onCloseEditor,
}: DraftCardProps) {
  const labels = useLabels(options)
  const missing = missingOf(row)
  const titleId = `draft-row-${row.key}`
  const activity = row.activity_id !== null ? labels.activity(row.activity_id) : undefined
  const flagged = missing.length > 0 || errors !== undefined

  return (
    <article
      className={`card card-border bg-base-100 ${flagged && !editing ? 'border-warning' : 'border-base-300'}`}
      aria-labelledby={titleId}
    >
      <div className="card-body gap-2 p-3 sm:p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h3 id={titleId} className="font-semibold">
            <span className="sr-only">Row {index + 1}: </span>
            {formatDayWithWeekday(row.log_date)}
          </h3>
          <Hours row={row} />
        </div>

        {editing ? (
          <LogFormBody log={null} isOwn draft={row} onApply={onApply} onDone={onCloseEditor} />
        ) : (
          <>
            <div className="min-w-0">
              <p className="font-medium break-words">
                {activity ?? <span className="text-base-content/80">No activity</span>}
              </p>
              <p className="mt-0.5 flex flex-wrap gap-x-2 gap-y-1 text-xs text-base-content/80">
                {row.project_id !== null && (
                  <span className="break-words">{labels.project(row.project_id)}</span>
                )}
                {row.category_id !== null && (
                  <span>
                    {row.project_id !== null && <span aria-hidden="true">· </span>}
                    {labels.category(row.category_id)}
                  </span>
                )}
                {row.om_project_id !== null && (
                  <span className="break-words">· O&M: {labels.omProject(row.om_project_id)}</span>
                )}
              </p>
              {row.description && (
                <p className="mt-1 line-clamp-3 text-sm break-words whitespace-pre-line">
                  {row.description}
                </p>
              )}
            </div>
            <p className="flex flex-wrap gap-1.5">
              {row.work_setup_id !== null && (
                <span className="badge badge-sm badge-outline">
                  {labels.workSetup(row.work_setup_id)}
                </span>
              )}
              {!row.is_planned && <span className="badge badge-sm badge-secondary">Unplanned</span>}
              {missing.length > 0 && (
                <span className="badge badge-sm badge-warning h-auto break-words">
                  Missing: {missing.join(', ')}
                </span>
              )}
              {checkHours(row) && (
                <span className="badge badge-sm badge-warning">Check hours: per day?</span>
              )}
            </p>
            {errors && (
              <div role="alert" className="alert alert-error py-2 text-sm">
                <span className="break-words">{errors.join(' ')}</span>
              </div>
            )}
            <div className="flex justify-end gap-1">
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={busy}
                onClick={onEdit}
                aria-describedby={titleId}
              >
                <PencilIcon className="size-4" />
                Edit
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={busy}
                onClick={onRemove}
                aria-describedby={titleId}
              >
                <TrashIcon className="size-4" />
                Remove
              </button>
            </div>
          </>
        )}
      </div>
    </article>
  )
}

function Hours({ row }: { row: DraftValues }) {
  const parts: string[] = []
  if (row.planned_hours !== null) parts.push(`${formatHours(row.planned_hours)} planned`)
  if (row.hours_spent !== null) parts.push(`${formatHours(row.hours_spent)} actual`)
  return (
    <span className="text-sm font-semibold tabular-nums">
      {parts.length ? parts.join(' · ') : <span className="font-normal">No hours</span>}
    </span>
  )
}

/** Labels of the active dropdown values by id (draft rows only hold active ids). */
function useLabels(options: LogOptions) {
  return useMemo(() => {
    const by = <T extends { id: number }>(rows: T[], text: (row: T) => string) => {
      const map = new Map(rows.map((row) => [row.id, text(row)]))
      return (id: number) => map.get(id) ?? '—'
    }
    return {
      activity: by(options.activities, (a) => a.label),
      project: by(options.projects, (p) => p.name),
      category: by(options.categories, (c) => c.label),
      omProject: by(options.om_projects, (o) => o.label),
      workSetup: by(options.work_setups, (w) => w.label),
    }
  }, [options])
}
