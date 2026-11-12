import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router'
import { z } from 'zod'

import {
  useCreateInvite,
  useInvites,
  useRegenerateInviteLink,
  useRevokeInvite,
  useTeamOptions,
  type Invite,
  type InviteCreated,
  type InviteStatus,
  type Team,
} from '../../api/admin'
import { errorMessage } from '../../api/client'
import ConfirmModal from '../../components/ConfirmModal'
import CopyLinkModal from '../../components/CopyLinkModal'
import DataTable, { type Column } from '../../components/DataTable'
import EmptyState from '../../components/EmptyState'
import { InputField, SelectField, SubmitButton } from '../../components/FormField'
import { LinkIcon, PlusIcon, TrashIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import Pagination from '../../components/Pagination'
import { useToast } from '../../components/toast-context'
import { applyFieldErrors } from '../../lib/forms'
import { formatDateTime } from '../../lib/format'
import { ROLE_LABEL } from '../../lib/labels'
import RoleBadge from './RoleBadge'

const STATUS_BADGE: Record<InviteStatus, { label: string; className: string }> = {
  pending: { label: 'Pending', className: 'badge-info' },
  accepted: { label: 'Accepted', className: 'badge-success' },
  expired: { label: 'Expired', className: 'badge-warning' },
}

const inviteSchema = z.object({
  email: z.string().trim().toLowerCase().email('Enter a valid email address').max(254),
  role: z.enum(['manager', 'dev']),
  team_id: z.string().min(1, 'Choose a team'),
})
type InviteForm = z.infer<typeof inviteSchema>

function InviteFormBody({
  teams,
  onCreated,
  onCancel,
}: {
  teams: Team[]
  onCreated: (invite: InviteCreated) => void
  onCancel: () => void
}) {
  const toast = useToast()
  const create = useCreateInvite()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<InviteForm>({
    resolver: zodResolver(inviteSchema),
    defaultValues: {
      email: '',
      role: 'dev',
      team_id: teams.length === 1 && teams[0] ? String(teams[0].id) : '',
    },
  })

  function onSubmit(data: InviteForm) {
    create.mutate(
      { ...data, team_id: Number(data.team_id) },
      {
        onSuccess: onCreated,
        onError: (error) => {
          if (!applyFieldErrors(error, setError, ['email', 'role', 'team_id'])) {
            toast.error(errorMessage(error))
          }
        },
      },
    )
  }

  if (teams.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        <p>Every invited user joins a team. Create a team first.</p>
        <div className="modal-action mt-0">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            Cancel
          </button>
          <Link to="/admin?tab=teams" className="btn btn-primary" onClick={onCancel}>
            Go to Teams
          </Link>
        </div>
      </div>
    )
  }

  return (
    <form onSubmit={(e) => void handleSubmit(onSubmit)(e)} noValidate>
      <InputField
        label="Email"
        type="email"
        autoFocus
        autoComplete="off"
        error={errors.email?.message}
        {...register('email')}
      />
      <div className="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
        <SelectField label="Role" error={errors.role?.message} {...register('role')}>
          <option value="dev">{ROLE_LABEL.dev}</option>
          <option value="manager">{ROLE_LABEL.manager}</option>
        </SelectField>
        <SelectField label="Team" error={errors.team_id?.message} {...register('team_id')}>
          <option value="">Choose a team</option>
          {teams.map((team) => (
            <option key={team.id} value={team.id}>
              {team.name}
            </option>
          ))}
        </SelectField>
      </div>
      <div className="modal-action">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
        <SubmitButton isPending={create.isPending}>Create invite</SubmitButton>
      </div>
    </form>
  )
}

export default function InvitesTab() {
  const toast = useToast()
  const [offset, setOffset] = useState(0)
  const invites = useInvites(offset)
  const teams = useTeamOptions()
  const regenerate = useRegenerateInviteLink()
  const revoke = useRevokeInvite()

  const [creating, setCreating] = useState(false)
  const [relinking, setRelinking] = useState<Invite | null>(null)
  const [revoking, setRevoking] = useState<Invite | null>(null)
  const [link, setLink] = useState<{ url: string; email: string; isNew: boolean } | null>(null)

  const teamName = (id: number) => teams.data?.find((team) => team.id === id)?.name ?? '—'

  function confirmRelink() {
    if (!relinking) return
    regenerate.mutate(relinking.id, {
      onSuccess: (invite) => {
        setRelinking(null)
        setLink({ url: invite.invite_url, email: invite.email, isNew: false })
      },
      onError: (error) => {
        setRelinking(null)
        toast.error(errorMessage(error))
        void invites.refetch()
      },
    })
  }

  function confirmRevoke() {
    if (!revoking) return
    revoke.mutate(revoking.id, {
      onSuccess: () => {
        toast.success(`Invite for ${revoking.email} revoked`)
        setRevoking(null)
      },
      onError: (error) => {
        toast.error(errorMessage(error))
        setRevoking(null)
      },
    })
  }

  const columns: Column<Invite>[] = [
    {
      key: 'email',
      header: 'Email',
      isTitle: true,
      cell: (invite) => <span className="break-all">{invite.email}</span>,
    },
    { key: 'role', header: 'Role', cell: (invite) => <RoleBadge role={invite.role} /> },
    { key: 'team', header: 'Team', cell: (invite) => teamName(invite.team_id) },
    {
      key: 'status',
      header: 'Status',
      cell: (invite) => {
        const badge = STATUS_BADGE[invite.status]
        return <span className={`badge badge-sm ${badge.className}`}>{badge.label}</span>
      },
    },
    {
      key: 'when',
      header: 'Expires / accepted',
      className: 'whitespace-nowrap',
      cell: (invite) =>
        invite.accepted_at
          ? `Accepted ${formatDateTime(invite.accepted_at)}`
          : formatDateTime(invite.expires_at),
    },
    {
      key: 'actions',
      header: 'Actions',
      hideLabelOnCard: true,
      className: 'md:text-right',
      cell: (invite) =>
        invite.status === 'accepted' ? null : (
          <div className="flex flex-wrap gap-2 md:flex-nowrap md:justify-end">
            {invite.status === 'pending' && (
              <button type="button" className="btn btn-sm" onClick={() => setRelinking(invite)}>
                <LinkIcon className="size-4" />
                Copy link
              </button>
            )}
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() => setRevoking(invite)}
            >
              <TrashIcon className="size-4" />
              Revoke
            </button>
          </div>
        ),
    },
  ]

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Invites</h2>
        <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
          <PlusIcon />
          New invite
        </button>
      </div>

      <DataTable
        caption="Invites"
        columns={columns}
        rows={invites.data?.items}
        rowKey={(invite) => invite.id}
        isLoading={invites.isPending}
        error={invites.error}
        onRetry={() => void invites.refetch()}
        empty={
          <EmptyState
            icon={<LinkIcon className="size-6" />}
            title="No invites yet"
            description="Invite a manager or developer. You copy the link and send it yourself."
          />
        }
      />
      {invites.data && (
        <Pagination
          total={invites.data.total}
          limit={invites.data.limit}
          offset={invites.data.offset}
          onChange={setOffset}
        />
      )}

      <Modal open={creating} title="New invite" onClose={() => setCreating(false)}>
        {teams.isPending ? (
          <span className="loading loading-spinner" aria-label="Loading teams" />
        ) : (
          <InviteFormBody
            teams={teams.data ?? []}
            onCancel={() => setCreating(false)}
            onCreated={(invite) => {
              setCreating(false)
              setLink({ url: invite.invite_url, email: invite.email, isNew: true })
            }}
          />
        )}
      </Modal>

      <ConfirmModal
        open={relinking !== null}
        title="Create a new invite link?"
        confirmLabel="Create link"
        tone="primary"
        isPending={regenerate.isPending}
        onConfirm={confirmRelink}
        onCancel={() => setRelinking(null)}
      >
        <p>
          Links are shown only once, so a new link is created for{' '}
          <strong className="break-all">{relinking?.email}</strong>. The previous link stops
          working. The expiry date does not change.
        </p>
      </ConfirmModal>

      <ConfirmModal
        open={revoking !== null}
        title="Revoke invite?"
        confirmLabel="Revoke"
        isPending={revoke.isPending}
        onConfirm={confirmRevoke}
        onCancel={() => setRevoking(null)}
      >
        <p>
          The link for <strong className="break-all">{revoking?.email}</strong> stops working. You
          can invite them again later.
        </p>
      </ConfirmModal>

      <CopyLinkModal
        url={link?.url ?? null}
        title={link?.isNew ? 'Invite created' : 'New invite link'}
        onClose={() => setLink(null)}
      >
        Send this link to <strong className="break-all">{link?.email}</strong>.
      </CopyLinkModal>
    </>
  )
}
