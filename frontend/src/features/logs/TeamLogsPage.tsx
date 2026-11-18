/*
 * /team/logs: logs written while their author was in the team (the team snapshot on
 * each log, so they stay here after someone changes teams).
 *
 * Managers see their own team, read-only. Admins pick any team and can edit or
 * delete logs; the backend enforces both.
 */
import { useState, type ReactNode } from 'react'

import { useTeamOptions } from '../../api/admin'
import { useCurrentUser } from '../../api/auth'
import { errorMessage } from '../../api/client'
import {
  useDeleteLog,
  useTeamLogs,
  useTeamMembers,
  type ProdLog,
  type ProdLogItem,
  type TeamLogFilters,
  type TeamMember,
} from '../../api/logs'
import AsyncState from '../../components/AsyncState'
import ConfirmModal from '../../components/ConfirmModal'
import EmptyState from '../../components/EmptyState'
import FilterPanel, { LookupFilter } from '../../components/FilterPanel'
import { InputField, SelectField } from '../../components/FormField'
import { ClockIcon, FilterIcon, PencilIcon, TrashIcon, UsersIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import PageHeader from '../../components/PageHeader'
import Pagination from '../../components/Pagination'
import { SkeletonForm } from '../../components/Skeleton'
import { useToast } from '../../components/toast-context'
import { formatDay } from '../../lib/format'
import { memberNote } from '../../lib/labels'
import LogFormBody from './LogForm'
import LogList, { LogListSkeleton } from './LogList'
import { logHours, logLabel } from './logText'

interface FilterState {
  member: string
  dateFrom: string
  dateTo: string
  project: string
  category: string
  activity: string
}

const NO_FILTERS: FilterState = {
  member: '',
  dateFrom: '',
  dateTo: '',
  project: '',
  category: '',
  activity: '',
}

const optionalId = (value: string) => (value ? Number(value) : undefined)

function toTeamFilters(f: FilterState): TeamLogFilters {
  return {
    user_id: optionalId(f.member),
    date_from: f.dateFrom || undefined,
    date_to: f.dateTo || undefined,
    project_id: optionalId(f.project),
    category_id: optionalId(f.category),
    activity_id: optionalId(f.activity),
  }
}

function memberLabel(member: TeamMember): string {
  const note = memberNote(member)
  return note ? `${member.username} (${note})` : member.username
}

function Filters({
  teamId,
  value,
  onChange,
}: {
  teamId: number
  value: FilterState
  onChange: (value: FilterState) => void
}) {
  const members = useTeamMembers(teamId)
  const activeCount = Object.values(value).filter(Boolean).length
  const set = (patch: Partial<FilterState>) => onChange({ ...value, ...patch })
  return (
    <FilterPanel activeCount={activeCount} onClear={() => onChange(NO_FILTERS)}>
      <SelectField
        label="Member"
        value={value.member}
        disabled={members.isPending}
        error={members.error ? 'Could not load the members' : undefined}
        onChange={(event) => set({ member: event.target.value })}
      >
        <option value="">Everyone</option>
        {members.data?.map((member) => (
          <option key={member.id} value={member.id}>
            {memberLabel(member)}
          </option>
        ))}
      </SelectField>
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
    </FilterPanel>
  )
}

export default function TeamLogsPage() {
  const me = useCurrentUser().data
  if (!me) return null
  return me.role === 'admin' ? (
    <AdminTeamLogs myId={me.id} />
  ) : (
    <TeamLogs
      teamId={me.team?.id}
      description={
        <>
          Read-only. Logs written while in <strong>{me.team?.name}</strong>, including by people who
          have since moved to another team.
        </>
      }
    />
  )
}

/** Admin: pick a team first. */
function AdminTeamLogs({ myId }: { myId: number }) {
  const teams = useTeamOptions()
  const [chosen, setChosen] = useState<number | undefined>(undefined)
  const teamId = chosen ?? teams.data?.[0]?.id

  const selector = (
    <AsyncState
      query={teams}
      isEmpty={teams.data?.length === 0}
      skeleton={<SkeletonForm fields={1} />}
      empty={
        <EmptyState
          icon={<UsersIcon className="size-6" />}
          title="No teams yet"
          description="Create a team under Admin to see its logs here."
        />
      }
    >
      {() => (
        <SelectField
          label="Team"
          wrapperClassName="mb-4 max-w-sm"
          value={teamId ?? ''}
          onChange={(event) => setChosen(Number(event.target.value))}
        >
          {teams.data?.map((team) => (
            <option key={team.id} value={team.id}>
              {team.name}
            </option>
          ))}
        </SelectField>
      )}
    </AsyncState>
  )

  return (
    <TeamLogs
      // Remount on team change: filters (members especially) belong to one team.
      key={teamId ?? 'none'}
      teamId={teamId}
      selector={selector}
      editorId={myId}
      description="Logs by team, as recorded when they were written. You can edit and delete them."
    />
  )
}

interface TeamLogsProps {
  teamId: number | undefined
  description: ReactNode
  selector?: ReactNode
  /** Set for admins: enables edit and delete. */
  editorId?: number
}

function TeamLogs({ teamId, description, selector, editorId }: TeamLogsProps) {
  const toast = useToast()
  const [filters, setFilters] = useState<FilterState>(NO_FILTERS)
  const [offset, setOffset] = useState(0)
  const logs = useTeamLogs(teamId, toTeamFilters(filters), offset)
  const remove = useDeleteLog()
  const [editing, setEditing] = useState<ProdLog | null>(null)
  const [deleting, setDeleting] = useState<ProdLogItem | null>(null)
  const canEdit = editorId !== undefined
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

  return (
    <>
      <PageHeader title="Team logs" description={description} />
      {selector}

      {teamId !== undefined && (
        <>
          <Filters teamId={teamId} value={filters} onChange={changeFilters} />
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
                  title="No logs for this team yet"
                  description="Logs appear here as team members record their work."
                />
              )
            }
          >
            {() => (
              <LogList
                logs={logs.data?.items ?? []}
                showAuthor
                totalLabel="Team total"
                actions={
                  canEdit
                    ? (log) => (
                        <>
                          <button
                            type="button"
                            className="btn btn-sm"
                            onClick={() => setEditing(log)}
                          >
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
                      )
                    : undefined
                }
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
        </>
      )}

      {canEdit && (
        <>
          <Modal open={editing !== null} title="Edit log" onClose={() => setEditing(null)}>
            {editing && (
              <LogFormBody
                log={editing}
                isOwn={editing.user.id === editorId}
                onDone={() => setEditing(null)}
              />
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
                <strong className="break-words">{logLabel(deleting)}</strong> by{' '}
                {deleting.user.username} ({logHours(deleting)} on {formatDay(deleting.log_date)})
                will be deleted. This cannot be undone.
              </p>
            )}
          </ConfirmModal>
        </>
      )}
    </>
  )
}
