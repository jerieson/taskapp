import { useState } from 'react'

import { errorMessage } from '../../api/client'
import { useDeleteLog, useLogs, type LogFilters, type ProdLogItem } from '../../api/logs'
import AsyncState from '../../components/AsyncState'
import ConfirmModal from '../../components/ConfirmModal'
import EmptyState from '../../components/EmptyState'
import FilterPanel, { LookupFilter } from '../../components/FilterPanel'
import { DateField } from '../../components/DateInput'
import {
  ClockIcon,
  CopyIcon,
  FilterIcon,
  PencilIcon,
  PlusIcon,
  TrashIcon,
} from '../../components/icons'
import PageHeader from '../../components/PageHeader'
import Pagination from '../../components/Pagination'
import { useToast } from '../../components/toast-context'
import { formatDay } from '../../lib/format'
import AiLogEntry from '../ai/AiLogEntry'
import { PlanReminder } from '../today/PlanningParts'
import ExportLogs from './ExportLogs'
import LogFormModal, { type LogModalState } from './LogFormModal'
import LogList, { LogListSkeleton } from './LogList'
import { logHours, logLabel } from './logText'

/** Form values for the filter controls ("" = not filtered). */
interface FilterState {
  dateFrom: string
  dateTo: string
  project: string
  category: string
  activity: string
}

const NO_FILTERS: FilterState = {
  dateFrom: '',
  dateTo: '',
  project: '',
  category: '',
  activity: '',
}

const optionalId = (value: string) => (value ? Number(value) : undefined)

function toLogFilters(f: FilterState): LogFilters {
  return {
    date_from: f.dateFrom || undefined,
    date_to: f.dateTo || undefined,
    project_id: optionalId(f.project),
    category_id: optionalId(f.category),
    activity_id: optionalId(f.activity),
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
      <DateField
        label="From"
        placeholder="Any date"
        clearable
        value={value.dateFrom}
        max={value.dateTo || undefined}
        onChange={(dateFrom) => set({ dateFrom })}
      />
      <DateField
        label="Until"
        placeholder="Any date"
        clearable
        value={value.dateTo}
        min={value.dateFrom || undefined}
        onChange={(dateTo) => set({ dateTo })}
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
    </FilterPanel>
  )
}

export default function LogsPage() {
  const toast = useToast()
  const [filters, setFilters] = useState<FilterState>(NO_FILTERS)
  const [offset, setOffset] = useState(0)
  const logs = useLogs(toLogFilters(filters), offset)
  const remove = useDeleteLog()
  const [modal, setModal] = useState<LogModalState | null>(null)
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
    <button type="button" className="btn btn-primary" onClick={() => setModal({ kind: 'new' })}>
      <PlusIcon />
      New log
    </button>
  )

  return (
    <>
      <PageHeader
        title="Logs"
        description="Your productivity log: planned hours ahead of time, actual hours afterwards."
        actions={
          <>
            <ExportLogs />
            {newButton}
          </>
        }
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
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => setModal({ kind: 'edit', log })}
                >
                  <PencilIcon className="size-4" />
                  Edit
                </button>
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => setModal({ kind: 'copy', log })}
                  aria-label={`Copy ${logLabel(log)} to other days`}
                >
                  <CopyIcon className="size-4" />
                  Copy
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

      <LogFormModal state={modal} onClose={() => setModal(null)} />

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
