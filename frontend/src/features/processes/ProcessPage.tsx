/*
 * /processes/:id: a process's steps, "Start run", and its runs with progress bars.
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router'
import { z } from 'zod'

import { ApiError, errorMessage } from '../../api/client'
import {
  useProcess,
  useProcessRuns,
  useStartRun,
  type Process,
  type ProcessStep,
} from '../../api/processes'
import AsyncState from '../../components/AsyncState'
import ColorDot from '../../components/ColorDot'
import EmptyState from '../../components/EmptyState'
import { InputField, SubmitButton } from '../../components/FormField'
import BackLink from '../../components/BackLink'
import { PencilIcon, PlayIcon, RepeatIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import PageHeader from '../../components/PageHeader'
import Pagination from '../../components/Pagination'
import { SkeletonCard, SkeletonPage } from '../../components/Skeleton'
import { useToast } from '../../components/toast-context'
import { formatDate, formatHours } from '../../lib/format'
import { isNotFound, useIdParam } from '../../lib/routing'
import NotFoundPage from '../../routes/NotFoundPage'
import { ProcessMenu } from './ProcessActions'
import ProcessFormBody from './ProcessForm'
import { processSummary } from './summary'
import { RunProgressBar, RunStatusBadge } from './RunBits'

export default function ProcessPage() {
  const id = useIdParam()
  if (id === null) return <NotFoundPage />
  return <ProcessView id={id} />
}

function ProcessView({ id }: { id: number }) {
  const navigate = useNavigate()
  const process = useProcess(id)
  const [editing, setEditing] = useState(false)
  const [starting, setStarting] = useState(false)

  if (isNotFound(process.error)) return <NotFoundPage />

  return (
    <AsyncState query={process} skeleton={<SkeletonPage />}>
      {() => {
        const p = process.data
        if (!p) return null
        const canStart = p.is_active && p.steps.length > 0
        return (
          <>
            <BackLink to="/processes">Processes</BackLink>
            <PageHeader
              title={p.name}
              description={p.description ?? undefined}
              actions={
                <>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => setStarting(true)}
                    disabled={!canStart}
                  >
                    <PlayIcon className="size-4" />
                    Start run
                  </button>
                  <button type="button" className="btn" onClick={() => setEditing(true)}>
                    <PencilIcon className="size-4" />
                    Edit
                  </button>
                </>
              }
            />

            {!p.is_active && (
              <div role="status" className="alert alert-warning mb-4">
                <span>This process is inactive. Activate it to start new runs.</span>
              </div>
            )}

            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-base-content/80">{processSummary(p)}</p>
              <div className="flex items-center gap-1">
                <ProcessMenu process={p} onDeleted={() => void navigate('/processes')} />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
              <StepsCard process={p} onEdit={() => setEditing(true)} />
              <RunsCard process={p} onStart={canStart ? () => setStarting(true) : undefined} />
            </div>

            <Modal open={editing} title="Edit process" onClose={() => setEditing(false)}>
              {editing && (
                <ProcessFormBody
                  processId={p.id}
                  onCancel={() => setEditing(false)}
                  onDone={() => setEditing(false)}
                />
              )}
            </Modal>
            <Modal open={starting} title="Start run" onClose={() => setStarting(false)}>
              {starting && <StartRunForm process={p} onCancel={() => setStarting(false)} />}
            </Modal>
          </>
        )
      }}
    </AsyncState>
  )
}

// ------------------------------------------------------------------ steps

function StepItem({ step, n }: { step: ProcessStep; n: number }) {
  return (
    <li className="flex gap-3 py-3">
      <span
        className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-content"
        aria-hidden="true"
      >
        {n}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="sr-only">Step {n}:</span>
        <span className="font-medium break-words">{step.title}</span>
        {(step.default_category || step.estimated_hours !== null) && (
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-base-content/80">
            {step.default_category && (
              <span className="inline-flex items-center gap-1">
                <ColorDot color={step.default_category.color} />
                {step.default_category.label}
                {!step.default_category.is_active && ' (inactive)'}
              </span>
            )}
            {step.estimated_hours !== null && (
              <span>Estimate {formatHours(step.estimated_hours)}</span>
            )}
          </span>
        )}
        {step.description && (
          <p className="text-sm break-words whitespace-pre-line text-base-content/80">
            {step.description}
          </p>
        )}
      </div>
    </li>
  )
}

function StepsCard({ process, onEdit }: { process: Process; onEdit: () => void }) {
  const estimate = process.steps.reduce((sum, s) => sum + (s.estimated_hours ?? 0), 0)
  return (
    <section
      aria-labelledby="steps-heading"
      className="card card-border border-base-300 bg-base-100 lg:col-span-2"
    >
      <div className="card-body p-4">
        <div className="flex items-baseline justify-between gap-2">
          <h2 id="steps-heading" className="card-title text-lg">
            Steps
          </h2>
          {estimate > 0 && (
            <span className="text-sm text-base-content/80">
              {formatHours(Math.round(estimate * 100) / 100)} estimated
            </span>
          )}
        </div>
        {process.steps.length === 0 ? (
          <EmptyState
            size="compact"
            title="No steps yet"
            description="Add at least one step to start a run."
            action={
              <button type="button" className="btn btn-sm" onClick={onEdit}>
                <PencilIcon className="size-4" />
                Add steps
              </button>
            }
          />
        ) : (
          <ol className="divide-y divide-base-300">
            {process.steps.map((step, index) => (
              <StepItem key={step.id} step={step} n={index + 1} />
            ))}
          </ol>
        )}
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ runs

function RunsCard({ process, onStart }: { process: Process; onStart?: () => void }) {
  const [offset, setOffset] = useState(0)
  const runs = useProcessRuns(process.id, offset)
  return (
    <section
      aria-labelledby="runs-heading"
      className="card card-border border-base-300 bg-base-100 lg:col-span-3"
    >
      <div className="card-body p-4">
        <h2 id="runs-heading" className="card-title text-lg">
          Runs
        </h2>
        <AsyncState
          query={runs}
          isEmpty={runs.data?.items.length === 0}
          skeleton={
            <div className="flex flex-col gap-3">
              <SkeletonCard lines={1} />
              <SkeletonCard lines={1} />
            </div>
          }
          empty={
            <EmptyState
              size="compact"
              icon={<RepeatIcon className="size-5" />}
              title="No runs yet"
              description="Start a run to copy the steps into your tasks."
              action={
                onStart && (
                  <button type="button" className="btn btn-sm btn-primary" onClick={onStart}>
                    <PlayIcon className="size-4" />
                    Start run
                  </button>
                )
              }
            />
          }
        >
          {() => (
            <ul className="flex flex-col gap-2">
              {runs.data?.items.map((run) => (
                <li key={run.id}>
                  <Link
                    to={`/runs/${run.id}`}
                    className="flex flex-col gap-2 rounded-box border border-base-300 p-3 transition-colors hover:bg-base-200 focus-visible:bg-base-200"
                  >
                    <span className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-medium">
                        Started {formatDate(run.started_at)}
                      </span>
                      <RunStatusBadge status={run.status} />
                    </span>
                    <RunProgressBar
                      run={run}
                      label={`Progress of the run started ${formatDate(run.started_at)}`}
                    />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </AsyncState>
        {runs.data && (
          <Pagination
            total={runs.data.total}
            limit={runs.data.limit}
            offset={runs.data.offset}
            onChange={setOffset}
          />
        )}
      </div>
    </section>
  )
}

// ------------------------------------------------------------------ start run

const startSchema = z.object({ due_date: z.string() })
type StartForm = z.infer<typeof startSchema>

function StartRunForm({ process, onCancel }: { process: Process; onCancel: () => void }) {
  const toast = useToast()
  const navigate = useNavigate()
  const start = useStartRun()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<StartForm>({ resolver: zodResolver(startSchema), defaultValues: { due_date: '' } })
  const count = process.steps.length

  function onSubmit(data: StartForm) {
    start.mutate(
      { processId: process.id, dueDate: data.due_date || null },
      {
        onSuccess: (run) => {
          toast.success(`Run started with ${count} ${count === 1 ? 'task' : 'tasks'}`)
          void navigate(`/runs/${run.id}`)
        },
        onError: (error) => {
          const message = error instanceof ApiError ? error.fields.due_date : undefined
          if (message) setError('due_date', { type: 'server', message })
          else toast.error(errorMessage(error))
        },
      },
    )
  }

  return (
    <form onSubmit={(e) => void handleSubmit(onSubmit)(e)} noValidate>
      <p className="text-sm">
        Creates {count} {count === 1 ? 'task' : 'tasks'} from the steps of{' '}
        <strong className="break-words">{process.name}</strong>, with the default status and
        priority.
      </p>
      <InputField
        label="Due date for all tasks (optional)"
        type="date"
        error={errors.due_date?.message}
        {...register('due_date')}
      />
      <div className="modal-action">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
        <SubmitButton isPending={start.isPending}>
          <PlayIcon className="size-4" />
          Start run
        </SubmitButton>
      </div>
    </form>
  )
}
