import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { useCreateTeam, useDeleteTeam, useRenameTeam, useTeams, type Team } from '../../api/admin'
import { errorMessage } from '../../api/client'
import ConfirmModal from '../../components/ConfirmModal'
import DataTable, { type Column } from '../../components/DataTable'
import EmptyState from '../../components/EmptyState'
import { InputField, SubmitButton } from '../../components/FormField'
import { PencilIcon, PlusIcon, TrashIcon, UsersIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import Pagination from '../../components/Pagination'
import { useToast } from '../../components/toast-context'
import { applyFieldErrors } from '../../lib/forms'
import { formatDate } from '../../lib/format'

const teamSchema = z.object({
  name: z.string().trim().min(1, 'Enter a team name').max(100, 'Use at most 100 characters'),
})
type TeamForm = z.infer<typeof teamSchema>

function TeamFormBody({ team, onDone }: { team: Team | null; onDone: () => void }) {
  const toast = useToast()
  const create = useCreateTeam()
  const rename = useRenameTeam()
  const mutation = team ? rename : create
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<TeamForm>({
    resolver: zodResolver(teamSchema),
    defaultValues: { name: team?.name ?? '' },
  })

  function onSubmit(data: TeamForm) {
    const options = {
      onSuccess: (saved: Team) => {
        toast.success(team ? `Renamed to “${saved.name}”` : `Team “${saved.name}” created`)
        onDone()
      },
      onError: (error: unknown) => {
        if (!applyFieldErrors(error, setError, ['name'])) toast.error(errorMessage(error))
      },
    }
    if (team) rename.mutate({ id: team.id, ...data }, options)
    else create.mutate(data, options)
  }

  return (
    <form onSubmit={(e) => void handleSubmit(onSubmit)(e)} noValidate>
      <InputField
        label="Team name"
        autoFocus
        autoComplete="off"
        error={errors.name?.message}
        {...register('name')}
      />
      <div className="modal-action">
        <button type="button" className="btn btn-ghost" onClick={onDone}>
          Cancel
        </button>
        <SubmitButton isPending={mutation.isPending}>{team ? 'Save' : 'Create team'}</SubmitButton>
      </div>
    </form>
  )
}

export default function TeamsTab() {
  const toast = useToast()
  const [offset, setOffset] = useState(0)
  const teams = useTeams(offset)
  const deleteTeam = useDeleteTeam()
  // undefined = closed, null = new team, Team = rename.
  const [editing, setEditing] = useState<Team | null | undefined>(undefined)
  const [deleting, setDeleting] = useState<Team | null>(null)

  function confirmDelete() {
    if (!deleting) return
    deleteTeam.mutate(deleting.id, {
      onSuccess: () => {
        toast.success(`Team “${deleting.name}” deleted`)
        setDeleting(null)
      },
      onError: (error) => {
        toast.error(errorMessage(error))
        setDeleting(null)
      },
    })
  }

  const columns: Column<Team>[] = [
    { key: 'name', header: 'Name', isTitle: true, cell: (team) => team.name },
    {
      key: 'members',
      header: 'Members',
      cell: (team) => team.member_count,
      className: 'md:w-28',
    },
    {
      key: 'created',
      header: 'Created',
      cell: (team) => formatDate(team.created_at),
      className: 'md:w-40',
    },
    {
      key: 'actions',
      header: 'Actions',
      hideLabelOnCard: true,
      className: 'md:text-right',
      cell: (team) => (
        <div className="flex flex-wrap gap-2 md:flex-nowrap md:justify-end">
          <button type="button" className="btn btn-sm" onClick={() => setEditing(team)}>
            <PencilIcon className="size-4" />
            Rename
          </button>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={() => setDeleting(team)}
            disabled={team.member_count > 0}
            title={team.member_count > 0 ? 'Move or deactivate its members first' : undefined}
          >
            <TrashIcon className="size-4" />
            Delete
          </button>
        </div>
      ),
    },
  ]

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Teams</h2>
        <button type="button" className="btn btn-primary" onClick={() => setEditing(null)}>
          <PlusIcon />
          New team
        </button>
      </div>

      <DataTable
        caption="Teams"
        columns={columns}
        rows={teams.data?.items}
        rowKey={(team) => team.id}
        isLoading={teams.isPending}
        error={teams.error}
        onRetry={() => void teams.refetch()}
        empty={
          <EmptyState
            icon={<UsersIcon className="size-6" />}
            title="No teams yet"
            description="Create a team before inviting managers and developers."
          />
        }
      />
      {teams.data && (
        <Pagination
          total={teams.data.total}
          limit={teams.data.limit}
          offset={teams.data.offset}
          onChange={setOffset}
        />
      )}

      <Modal
        open={editing !== undefined}
        title={editing ? 'Rename team' : 'New team'}
        onClose={() => setEditing(undefined)}
      >
        {editing !== undefined && (
          <TeamFormBody team={editing} onDone={() => setEditing(undefined)} />
        )}
      </Modal>

      <ConfirmModal
        open={deleting !== null}
        title="Delete team?"
        confirmLabel="Delete"
        isPending={deleteTeam.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setDeleting(null)}
      >
        <p>
          Delete <strong>{deleting?.name}</strong>? Its pending invites are removed too. A team that
          has prod logs cannot be deleted.
        </p>
      </ConfirmModal>
    </>
  )
}
