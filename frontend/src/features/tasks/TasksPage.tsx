import { useState } from 'react'

import { errorMessage } from '../../api/client'
import {
  useDeleteTask,
  useTasks,
  type Task,
  type TaskFilters,
  type TaskSort,
  type TaskState,
} from '../../api/tasks'
import { DateField } from '../../components/DateInput'
import ColorDot from '../../components/ColorDot'
import ConfirmModal from '../../components/ConfirmModal'
import DataTable, { type Column } from '../../components/DataTable'
import EmptyState from '../../components/EmptyState'
import FilterPanel, { LookupFilter } from '../../components/FilterPanel'
import { SelectField } from '../../components/FormField'
import {
  CheckSquareIcon,
  FilterIcon,
  PencilIcon,
  PlusIcon,
  TrashIcon,
} from '../../components/icons'
import Modal from '../../components/Modal'
import PageHeader from '../../components/PageHeader'
import Pagination from '../../components/Pagination'
import { useToast } from '../../components/toast-context'
import { DueCell, StatusQuickSelect, TaskTitle } from './TaskCells'
import TaskFormBody from './TaskForm'

// ------------------------------------------------------------------ filters

/** Form values for the filter controls ("" = not filtered). */
interface FilterState {
  status: string
  priority: string
  project: string
  category: string
  dueFrom: string
  dueTo: string
  source: string
}

const NO_FILTERS: FilterState = {
  status: '',
  priority: '',
  project: '',
  category: '',
  dueFrom: '',
  dueTo: '',
  source: '',
}

type StateTab = TaskState | 'all'

const STATE_TABS: { value: StateTab; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'completed', label: 'Completed' },
  { value: 'all', label: 'All' },
]

const SORTS: { value: TaskSort; label: string }[] = [
  { value: 'due_date', label: 'Due date: soonest first' },
  { value: '-due_date', label: 'Due date: latest first' },
  { value: 'priority', label: 'Priority: highest first' },
  { value: '-priority', label: 'Priority: lowest first' },
  { value: '-created_at', label: 'Newest first' },
  { value: 'created_at', label: 'Oldest first' },
]

const optionalId = (value: string) => (value ? Number(value) : undefined)

function toTaskFilters(state: StateTab, f: FilterState): TaskFilters {
  return {
    state: state === 'all' ? undefined : state,
    status_id: optionalId(f.status),
    priority_id: optionalId(f.priority),
    project_id: optionalId(f.project),
    category_id: optionalId(f.category),
    due_from: f.dueFrom || undefined,
    due_to: f.dueTo || undefined,
    in_process_run: f.source ? f.source === 'run' : undefined,
  }
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
      <LookupFilter
        kind="statuses"
        label="Status"
        allLabel="Any status"
        value={value.status}
        onChange={(status) => set({ status })}
      />
      <LookupFilter
        kind="priorities"
        label="Priority"
        allLabel="Any priority"
        value={value.priority}
        onChange={(priority) => set({ priority })}
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
      <DateField
        label="Due from"
        placeholder="Any date"
        clearable
        value={value.dueFrom}
        max={value.dueTo || undefined}
        onChange={(dueFrom) => set({ dueFrom })}
      />
      <DateField
        label="Due until"
        placeholder="Any date"
        clearable
        value={value.dueTo}
        min={value.dueFrom || undefined}
        onChange={(dueTo) => set({ dueTo })}
      />
      <SelectField
        label="Source"
        value={value.source}
        onChange={(event) => set({ source: event.target.value })}
      >
        <option value="">All tasks</option>
        <option value="run">From a process run</option>
        <option value="standalone">Not from a process run</option>
      </SelectField>
    </FilterPanel>
  )
}

// ------------------------------------------------------------------ page

export default function TasksPage() {
  const toast = useToast()
  const [stateTab, setStateTab] = useState<StateTab>('open')
  const [filters, setFilters] = useState<FilterState>(NO_FILTERS)
  const [sort, setSort] = useState<TaskSort>('due_date')
  const [offset, setOffset] = useState(0)
  const tasks = useTasks(toTaskFilters(stateTab, filters), sort, offset)
  const remove = useDeleteTask()
  // undefined = closed, null = new task, Task = edit.
  const [editing, setEditing] = useState<Task | null | undefined>(undefined)
  const [deleting, setDeleting] = useState<Task | null>(null)

  const hasFilters = Object.values(filters).some(Boolean)

  function changeFilters(next: FilterState) {
    setFilters(next)
    setOffset(0)
  }

  function confirmDelete() {
    if (!deleting) return
    const task = deleting
    remove.mutate(task.id, {
      onSuccess: () => toast.success(`“${task.title}” deleted`),
      onError: (error) => toast.error(errorMessage(error)),
      onSettled: () => setDeleting(null),
    })
  }

  const newButton = (
    <button type="button" className="btn btn-primary" onClick={() => setEditing(null)}>
      <PlusIcon />
      New task
    </button>
  )

  const columns: Column<Task>[] = [
    {
      key: 'title',
      header: 'Task',
      isTitle: true,
      cell: (task) => <TaskTitle task={task} showRunLink />,
    },
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
    {
      key: 'due',
      header: 'Due',
      className: 'md:w-44',
      cell: (task) => <DueCell task={task} />,
    },
    {
      key: 'actions',
      header: 'Actions',
      hideLabelOnCard: true,
      className: 'md:text-right md:w-40',
      cell: (task) => (
        <div className="flex flex-wrap gap-2 md:flex-nowrap md:justify-end">
          <button type="button" className="btn btn-sm" onClick={() => setEditing(task)}>
            <PencilIcon className="size-4" />
            Edit
          </button>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={() => setDeleting(task)}
            aria-label={`Delete ${task.title}`}
          >
            <TrashIcon className="size-4" />
            <span className="md:hidden">Delete</span>
          </button>
        </div>
      ),
    },
  ]

  return (
    <>
      <PageHeader title="Tasks" description="Your own tasks." actions={newButton} />

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div role="tablist" aria-label="Show" className="tabs tabs-box w-full sm:w-auto">
          {STATE_TABS.map((tab) => (
            <button
              key={tab.value}
              type="button"
              role="tab"
              aria-selected={stateTab === tab.value}
              className={`tab flex-1 sm:flex-none ${stateTab === tab.value ? 'tab-active' : 'text-base-content/80'}`}
              onClick={() => {
                setStateTab(tab.value)
                setOffset(0)
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <span className="shrink-0 text-base-content/80">Sort</span>
          <select
            className="select w-full sm:w-60"
            value={sort}
            onChange={(event) => {
              const next = SORTS.find((s) => s.value === event.target.value)
              if (next) {
                setSort(next.value)
                setOffset(0)
              }
            }}
          >
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <Filters value={filters} onChange={changeFilters} />

      <DataTable
        caption="Tasks"
        columns={columns}
        rows={tasks.data?.items}
        rowKey={(task) => task.id}
        isLoading={tasks.isPending}
        error={tasks.error}
        onRetry={() => void tasks.refetch()}
        empty={
          hasFilters ? (
            <EmptyState
              icon={<FilterIcon className="size-6" />}
              title="No tasks match these filters"
              action={
                <button type="button" className="btn" onClick={() => changeFilters(NO_FILTERS)}>
                  Clear filters
                </button>
              }
            />
          ) : (
            <EmptyState
              icon={<CheckSquareIcon className="size-6" />}
              title={
                stateTab === 'open'
                  ? 'No open tasks'
                  : stateTab === 'completed'
                    ? 'No completed tasks yet'
                    : 'No tasks yet'
              }
              description="Plan your work as tasks, then log time against them."
              action={newButton}
            />
          )
        }
      />
      {tasks.data && (
        <Pagination
          total={tasks.data.total}
          limit={tasks.data.limit}
          offset={tasks.data.offset}
          onChange={setOffset}
        />
      )}

      <Modal
        open={editing !== undefined}
        title={editing ? 'Edit task' : 'New task'}
        onClose={() => setEditing(undefined)}
      >
        {editing !== undefined && (
          <TaskFormBody task={editing} onDone={() => setEditing(undefined)} />
        )}
      </Modal>

      <ConfirmModal
        open={deleting !== null}
        title="Delete task?"
        confirmLabel="Delete"
        isPending={remove.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setDeleting(null)}
      >
        <p>
          <strong className="break-words">{deleting?.title}</strong> will be deleted. Prod logs for
          it keep their hours but are no longer linked to it. This cannot be undone.
        </p>
      </ConfirmModal>
    </>
  )
}
