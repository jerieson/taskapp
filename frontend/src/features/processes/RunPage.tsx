/*
 * /runs/:id: a process run's tasks with quick status changes and progress.
 *
 * The run completes on its own when every task is done and reopens when one is
 * reopened (backend). Cancelling keeps the tasks.
 */
import { useState } from 'react'

import { errorMessage } from '../../api/client'
import { useCancelRun, useRun, type RunDetail } from '../../api/processes'
import type { Task } from '../../api/tasks'
import AsyncState from '../../components/AsyncState'
import BackLink from '../../components/BackLink'
import ColorDot from '../../components/ColorDot'
import ConfirmModal from '../../components/ConfirmModal'
import DataTable, { type Column } from '../../components/DataTable'
import EmptyState from '../../components/EmptyState'
import { CheckSquareIcon, PencilIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import PageHeader from '../../components/PageHeader'
import { SkeletonPage } from '../../components/Skeleton'
import { useToast } from '../../components/toast-context'
import { formatDateTime } from '../../lib/format'
import { isNotFound, useIdParam } from '../../lib/routing'
import NotFoundPage from '../../routes/NotFoundPage'
import { DueCell, StatusQuickSelect, TaskTitle } from '../tasks/TaskCells'
import TaskFormBody from '../tasks/TaskForm'
import { RunProgressBar, RunStatusBadge } from './RunBits'

export default function RunPage() {
  const id = useIdParam()
  if (id === null) return <NotFoundPage />
  return <RunView id={id} />
}

function RunView({ id }: { id: number }) {
  const run = useRun(id)
  if (isNotFound(run.error)) return <NotFoundPage />
  return (
    <AsyncState query={run} skeleton={<SkeletonPage />}>
      {() => run.data && <RunContent run={run.data} />}
    </AsyncState>
  )
}

function RunSummary({ run }: { run: RunDetail }) {
  return (
    <section
      aria-label="Run progress"
      className="card card-border mb-4 border-base-300 bg-base-100"
    >
      <div className="card-body gap-3 p-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <RunStatusBadge status={run.status} />
          <span className="text-base-content/80">Started {formatDateTime(run.started_at)}</span>
          {run.completed_at && (
            <span className="text-base-content/80">
              Completed {formatDateTime(run.completed_at)}
            </span>
          )}
        </div>
        <RunProgressBar run={run} label="Run progress" />
        <p className="text-sm text-base-content/80">
          {run.status === 'cancelled'
            ? 'This run was cancelled. Its tasks are kept and can still be changed.'
            : run.status === 'completed'
              ? 'Every task is done. Reopening a task puts the run back in progress.'
              : 'The run completes on its own when every task is done.'}
        </p>
      </div>
    </section>
  )
}

function RunContent({ run }: { run: RunDetail }) {
  const toast = useToast()
  const cancel = useCancelRun()
  const [confirming, setConfirming] = useState(false)
  const [editing, setEditing] = useState<Task | null>(null)

  function confirmCancel() {
    cancel.mutate(run.id, {
      onSuccess: () => toast.success('Run cancelled'),
      onError: (error) => toast.error(errorMessage(error)),
      onSettled: () => setConfirming(false),
    })
  }

  const columns: Column<Task>[] = [
    { key: 'title', header: 'Task', isTitle: true, cell: (task) => <TaskTitle task={task} /> },
    {
      key: 'status',
      header: 'Status',
      className: 'md:w-52',
      cell: (task) => <StatusQuickSelect task={task} />,
    },
    {
      key: 'priority',
      header: 'Priority',
      className: 'md:w-36',
      cell: (task) => (
        <span className="inline-flex items-center gap-2">
          <ColorDot color={task.priority.color} />
          {task.priority.label}
        </span>
      ),
    },
    { key: 'due', header: 'Due', className: 'md:w-44', cell: (task) => <DueCell task={task} /> },
    {
      key: 'actions',
      header: 'Actions',
      hideLabelOnCard: true,
      className: 'md:text-right md:w-28',
      cell: (task) => (
        <button type="button" className="btn btn-sm" onClick={() => setEditing(task)}>
          <PencilIcon className="size-4" />
          Edit
        </button>
      ),
    },
  ]

  return (
    <>
      <BackLink to={`/processes/${run.process.id}`}>{run.process.name}</BackLink>
      <PageHeader
        title={run.process.name}
        description="Process run"
        actions={
          run.status === 'in_progress' && (
            <button type="button" className="btn" onClick={() => setConfirming(true)}>
              Cancel run
            </button>
          )
        }
      />

      <RunSummary run={run} />

      <h2 className="mb-3 text-lg font-semibold">Tasks</h2>
      <DataTable
        caption="Tasks of this run"
        columns={columns}
        rows={run.tasks}
        rowKey={(task) => task.id}
        empty={
          <EmptyState
            icon={<CheckSquareIcon className="size-6" />}
            title="No tasks left"
            description="The tasks of this run have been deleted."
          />
        }
      />

      <Modal open={editing !== null} title="Edit task" onClose={() => setEditing(null)}>
        {editing && <TaskFormBody task={editing} onDone={() => setEditing(null)} />}
      </Modal>

      <ConfirmModal
        open={confirming}
        title="Cancel run?"
        confirmLabel="Cancel run"
        isPending={cancel.isPending}
        onConfirm={confirmCancel}
        onCancel={() => setConfirming(false)}
      >
        <p>
          The run stops counting toward progress. Its {run.tasks.length}{' '}
          {run.tasks.length === 1 ? 'task stays' : 'tasks stay'} in your task list unchanged. A
          cancelled run cannot be resumed.
        </p>
      </ConfirmModal>
    </>
  )
}
