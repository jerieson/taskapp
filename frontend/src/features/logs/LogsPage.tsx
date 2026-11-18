import { useState } from 'react'

import { errorMessage } from '../../api/client'
import {
  useDeleteLog,
  useLogs,
  type LogFilters,
  type ProdLog,
  type ProdLogItem,
} from '../../api/logs'
import { useTaskOptions } from '../../api/tasks'
import AsyncState from '../../components/AsyncState'
import ConfirmModal from '../../components/ConfirmModal'
import EmptyState from '../../components/EmptyState'
import FilterPanel, { LookupFilter } from '../../components/FilterPanel'
import { InputField, SelectField } from '../../components/FormField'
import { ClockIcon, FilterIcon, PencilIcon, PlusIcon, TrashIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import PageHeader from '../../components/PageHeader'
import Pagination from '../../components/Pagination'
import { useToast } from '../../components/toast-context'
import { formatDay } from '../../lib/format'
import AiLogEntry from '../ai/AiLogEntry'
import { PlanReminder } from '../today/PlanningParts'
import LogFormBody from './LogForm'
import LogList, { LogListSkeleton } from './LogList'
import { logHours, logLabel } from './logText'

/** Form values for the filter controls ("" = not filtered). */
interface FilterState {
  dateFrom: string
  dateTo: string
  project: string
  category: string
  activity: string
  task: string
}

const NO_FILTERS: FilterState = {
  dateFrom: '',
  dateTo: '',
  project: '',
  category: '',
  activity: '',
  task: '',
}

const optionalId = (value: string) => (value ? Number(value) : undefined)

function toLogFilters(f: FilterState): LogFilters {
  return {
    date_from: f.dateFrom || undefined,
    date_to: f.dateTo || undefined,
    project_id: optionalId(f.project),
    category_id: optionalId(f.category),
    activity_id: optionalId(f.activity),
    task_id: optionalId(f.task),
  }
}

function TaskFilter({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const tasks = useTaskOptions(false)
  return (
    <SelectField
      label="Task"
      value={value}
      disabled={tasks.isPending}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">Any task</option>
      {tasks.data?.map((task) => (
        <option key={task.id} value={task.id}>
          {task.title}
        </option>
      ))}
    </SelectField>
  )
}

function Filters({
  value,
  onChange,
}: {
  value: FilterState
  onChange: (value: FilterState) => void
}) {
  const activeCount = Object.values(value).filter(Boolean).length
  const set = (patch: Partial<FilterState>) => onChange({ ...value, ...patch })
  return (
    <FilterPanel activeCount={activeCount} onClear={() => onChange(NO_FILTERS)}>
      <InputField
        label="From"
        type="date"
        value={value.dateFrom}
        max={value.dateTo || undefined}
        onChange={(event) => set({ dateFrom: event.target.value })}
      />
      <InputField
        label="Until"
        type="date"
        value={value.dateTo}
        min={value.dateFrom || undefined}
        onChange={(event) => set({ dateTo: event.target.value })}
      />
      <LookupFilter
        kind="projects"
        label="Project"
        allLabel="Any project"
        value={value.project}
        onChange={(project) => set({ project })}
      />
      <LookupFilter
        kind="categories"
        label="Category"
        allLabel="Any category"
        value={value.category}
        onChange={(category) => set({ category })}
      />
      <LookupFilter
        kind="activities"
        label="Activity"
        allLabel="Any activity"
        value={value.activity}
        onChange={(activity) => set({ activity })}
      />
      <TaskFilter value={value.task} onChange={(task) => set({ task })} />
    </FilterPanel>
  )
}

export default function LogsPage() {
  const toast = useToast()
  const [filters, setFilters] = useState<FilterState>(NO_FILTERS)
  const [offset, setOffset] = useState(0)
  const logs = useLogs(toLogFilters(filters), offset)
  const remove = useDeleteLog()
  // undefined = closed, null = new log, ProdLog = edit.
  const [editing, setEditing] = useState<ProdLog | null | undefined>(undefined)
  const [deleting, setDeleting] = useState<ProdLogItem | null>(null)

  const hasFilters = Object.values(filters).some(Boolean)

  function changeFilters(next: FilterState) {
    setFilters(next)
    setOffset(0)
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

  const newButton = (
    <button type="button" className="btn btn-primary" onClick={() => setEditing(null)}>
      <PlusIcon />
      New log
    </button>
  )

  return (
    <>
      <PageHeader
        title="Logs"
        description="Your productivity log: planned hours ahead of time, actual hours afterwards. A day can hold at most 24 planned and 24 actual hours."
        actions={newButton}
      />

      <PlanReminder className="mb-4" />

      <AiLogEntry className="mb-4" />

      <Filters value={filters} onChange={changeFilters} />

      <AsyncState
        query={logs}
        isEmpty={logs.data?.items.length === 0}
        skeleton={<LogListSkeleton />}
        empty={
          hasFilters ? (
            <EmptyState
              icon={<FilterIcon className="size-6" />}
              title="No logs match these filters"
              action={
                <button type="button" className="btn" onClick={() => changeFilters(NO_FILTERS)}>
                  Clear filters
                </button>
              }
            />
          ) : (
            <EmptyState
              icon={<ClockIcon className="size-6" />}
              title="No logs yet"
              description="Plan your hours ahead of time and record the actual hours afterwards."
              action={newButton}
            />
          )
        }
      >
        {() => (
          <LogList
            logs={logs.data?.items ?? []}
            totalLabel="Total"
            actions={(log) => (
              <>
                <button type="button" className="btn btn-sm" onClick={() => setEditing(log)}>
                  <PencilIcon className="size-4" />
                  Edit
                </button>
                <button
                  type="button"
                  className="btn btn-sm btn-ghost"
                  onClick={() => setDeleting(log)}
                  aria-label={`Delete ${logLabel(log)}`}
                >
                  <TrashIcon className="size-4" />
                  <span className="sm:hidden">Delete</span>
                </button>
              </>
            )}
          />
        )}
      </AsyncState>
      {logs.data && (
        <Pagination
          total={logs.data.total}
          limit={logs.data.limit}
          offset={logs.data.offset}
          onChange={setOffset}
        />
      )}

      <Modal
        open={editing !== undefined}
        title={editing ? 'Edit log' : 'New log'}
        onClose={() => setEditing(undefined)}
      >
        {editing !== undefined && (
          <LogFormBody log={editing} isOwn onDone={() => setEditing(undefined)} />
        )}
      </Modal>

      <ConfirmModal
        open={deleting !== null}
        title="Delete log?"
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
