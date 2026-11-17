/*
 * /processes: the user's own reusable processes (step templates).
 *
 * Active and inactive processes are on separate tabs. Each card links to the
 * process page, where runs are started.
 */
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { useProcesses, type ProcessListItem } from '../../api/processes'
import AsyncState from '../../components/AsyncState'
import EmptyState from '../../components/EmptyState'
import { PencilIcon, PlusIcon, RepeatIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import PageHeader from '../../components/PageHeader'
import Pagination from '../../components/Pagination'
import { SkeletonCard } from '../../components/Skeleton'
import { ProcessMenu } from './ProcessActions'
import ProcessFormBody from './ProcessForm'
import { processSummary } from './summary'

type Tab = 'active' | 'inactive'

function ListSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      <SkeletonCard lines={2} />
      <SkeletonCard lines={2} />
      <SkeletonCard lines={2} />
    </div>
  )
}

function ProcessCard({ process, onEdit }: { process: ProcessListItem; onEdit: () => void }) {
  return (
    <li className="card card-border border-base-300 bg-base-100">
      <div className="card-body gap-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <Link
            to={`/processes/${process.id}`}
            className="card-title min-w-0 text-base break-words link-hover"
          >
            {process.name}
          </Link>
          {!process.is_active && <span className="badge shrink-0 badge-neutral">Inactive</span>}
        </div>
        {process.description && (
          <p className="line-clamp-2 text-sm break-words text-base-content/80">
            {process.description}
          </p>
        )}
        <p className="text-sm text-base-content/80">{processSummary(process)}</p>
        <div className="card-actions mt-1 items-center justify-between">
          <Link to={`/processes/${process.id}`} className="btn btn-sm btn-primary">
            Open
          </Link>
          <div className="flex items-center gap-1">
            <button type="button" className="btn btn-sm" onClick={onEdit}>
              <PencilIcon className="size-4" />
              Edit
            </button>
            <ProcessMenu process={process} />
          </div>
        </div>
      </div>
    </li>
  )
}

export default function ProcessesPage() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('active')
  const [offset, setOffset] = useState(0)
  const processes = useProcesses(tab === 'active', offset)
  // undefined = closed, null = new process, number = edit that process.
  const [editing, setEditing] = useState<number | null | undefined>(undefined)

  const newButton = (
    <button type="button" className="btn btn-primary" onClick={() => setEditing(null)}>
      <PlusIcon />
      New process
    </button>
  )

  return (
    <>
      <PageHeader
        title="Processes"
        description="Reusable checklists. Starting a run turns each step into a task."
        actions={newButton}
      />

      <div role="tablist" aria-label="Show" className="tabs tabs-box mb-4 w-full sm:w-auto">
        {(['active', 'inactive'] as const).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            className={`tab flex-1 sm:flex-none ${tab === value ? 'tab-active' : 'text-base-content/80'}`}
            onClick={() => {
              setTab(value)
              setOffset(0)
            }}
          >
            {value === 'active' ? 'Active' : 'Inactive'}
          </button>
        ))}
      </div>

      <AsyncState
        query={processes}
        isEmpty={processes.data?.items.length === 0}
        skeleton={<ListSkeleton />}
        empty={
          tab === 'active' ? (
            <EmptyState
              icon={<RepeatIcon className="size-6" />}
              title="No processes yet"
              description="Save the steps you repeat (a release, an onboarding, a review) and start a run whenever you need them."
              action={newButton}
            />
          ) : (
            <EmptyState
              icon={<RepeatIcon className="size-6" />}
              title="No inactive processes"
              description="Processes you deactivate are kept here with their runs."
            />
          )
        }
      >
        {() => (
          <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {processes.data?.items.map((process) => (
              <ProcessCard
                key={process.id}
                process={process}
                onEdit={() => setEditing(process.id)}
              />
            ))}
          </ul>
        )}
      </AsyncState>
      {processes.data && (
        <Pagination
          total={processes.data.total}
          limit={processes.data.limit}
          offset={processes.data.offset}
          onChange={setOffset}
        />
      )}

      <Modal
        open={editing !== undefined}
        title={editing ? 'Edit process' : 'New process'}
        onClose={() => setEditing(undefined)}
      >
        {editing !== undefined && (
          <ProcessFormBody
            processId={editing}
            onCancel={() => setEditing(undefined)}
            onDone={(saved) => {
              setEditing(undefined)
              if (editing === null) void navigate(`/processes/${saved.id}`)
            }}
          />
        )}
      </Modal>
    </>
  )
}
