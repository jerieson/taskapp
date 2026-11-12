import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'

import {
  useCreatePasswordReset,
  useSetUserActive,
  useTeamOptions,
  useUpdateUser,
  useUsers,
  type AdminUser,
  type Team,
  type UserFilters,
} from '../../api/admin'
import { useCurrentUser, type Role } from '../../api/auth'
import { errorMessage } from '../../api/client'
import ConfirmModal from '../../components/ConfirmModal'
import CopyLinkModal from '../../components/CopyLinkModal'
import DataTable, { type Column } from '../../components/DataTable'
import EmptyState from '../../components/EmptyState'
import { SelectField, SubmitButton } from '../../components/FormField'
import { FilterIcon, KeyIcon, PencilIcon, UsersIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import Pagination from '../../components/Pagination'
import { useToast } from '../../components/toast-context'
import { applyFieldErrors } from '../../lib/forms'
import { formatDateTime } from '../../lib/format'
import { ROLE_LABEL } from '../../lib/labels'
import RoleBadge from './RoleBadge'

const ROLES: Role[] = ['admin', 'manager', 'dev']

// ------------------------------------------------------------------ filters

interface FilterState {
  team: string
  role: string
  status: string
}

const NO_FILTERS: FilterState = { team: '', role: '', status: '' }

function toUserFilters(state: FilterState): UserFilters {
  return {
    team_id: state.team ? Number(state.team) : undefined,
    role: ROLES.find((role) => role === state.role),
    is_active: state.status ? state.status === 'active' : undefined,
  }
}

function Filters({
  value,
  teams,
  onChange,
}: {
  value: FilterState
  teams: Team[]
  onChange: (value: FilterState) => void
}) {
  const [open, setOpen] = useState(false)
  const activeCount = Object.values(value).filter(Boolean).length

  return (
    <div className="mb-4">
      <button
        type="button"
        className="btn w-full md:hidden"
        aria-expanded={open}
        aria-controls="user-filters"
        onClick={() => setOpen((o) => !o)}
      >
        <FilterIcon />
        Filters
        {activeCount > 0 && <span className="badge badge-sm badge-primary">{activeCount}</span>}
      </button>
      <div
        id="user-filters"
        className={`${open ? 'grid' : 'hidden'} mt-2 grid-cols-1 gap-x-3 md:mt-0 md:grid md:grid-cols-4 md:items-end`}
      >
        <SelectField
          label="Team"
          value={value.team}
          onChange={(event) => onChange({ ...value, team: event.target.value })}
        >
          <option value="">All teams</option>
          {teams.map((team) => (
            <option key={team.id} value={team.id}>
              {team.name}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Role"
          value={value.role}
          onChange={(event) => onChange({ ...value, role: event.target.value })}
        >
          <option value="">All roles</option>
          {ROLES.map((role) => (
            <option key={role} value={role}>
              {ROLE_LABEL[role]}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Status"
          value={value.status}
          onChange={(event) => onChange({ ...value, status: event.target.value })}
        >
          <option value="">Any status</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </SelectField>
        <div className="fieldset">
          <button
            type="button"
            className="btn btn-ghost"
            disabled={activeCount === 0}
            onClick={() => onChange(NO_FILTERS)}
          >
            Clear filters
          </button>
        </div>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ edit form

const userSchema = z
  .object({
    role: z.enum(['admin', 'manager', 'dev']),
    team_id: z.string(),
  })
  .refine((data) => data.role === 'admin' || data.team_id !== '', {
    message: 'Managers and developers need a team',
    path: ['team_id'],
  })
type UserForm = z.infer<typeof userSchema>

function EditUserBody({
  user,
  teams,
  onDone,
}: {
  user: AdminUser
  teams: Team[]
  onDone: () => void
}) {
  const toast = useToast()
  const update = useUpdateUser()
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors },
  } = useForm<UserForm>({
    resolver: zodResolver(userSchema),
    defaultValues: { role: user.role, team_id: user.team ? String(user.team.id) : '' },
  })
  const role = useWatch({ control, name: 'role' })

  function onSubmit(data: UserForm) {
    const body =
      data.role === 'admin' ? { role: data.role } : { ...data, team_id: Number(data.team_id) }
    update.mutate(
      { id: user.id, ...body },
      {
        onSuccess: () => {
          toast.success(`${user.username} updated`)
          onDone()
        },
        onError: (error) => {
          if (!applyFieldErrors(error, setError, ['role', 'team_id'])) {
            toast.error(errorMessage(error))
          }
        },
      },
    )
  }

  return (
    <form onSubmit={(e) => void handleSubmit(onSubmit)(e)} noValidate>
      <SelectField label="Role" error={errors.role?.message} {...register('role')}>
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {ROLE_LABEL[r]}
          </option>
        ))}
      </SelectField>
      {role === 'admin' ? (
        <p className="mt-3 text-sm text-base-content/80">Admins do not belong to a team.</p>
      ) : (
        <SelectField label="Team" error={errors.team_id?.message} {...register('team_id')}>
          <option value="">Choose a team</option>
          {teams.map((team) => (
            <option key={team.id} value={team.id}>
              {team.name}
            </option>
          ))}
        </SelectField>
      )}
      <div className="modal-action">
        <button type="button" className="btn btn-ghost" onClick={onDone}>
          Cancel
        </button>
        <SubmitButton isPending={update.isPending}>Save</SubmitButton>
      </div>
    </form>
  )
}

// ------------------------------------------------------------------ tab

function signInMethods(user: AdminUser): string {
  if (user.has_password && user.google_linked) return 'Password, Google'
  return user.google_linked ? 'Google' : 'Password'
}

export default function UsersTab() {
  const toast = useToast()
  const me = useCurrentUser().data
  const [filters, setFilters] = useState<FilterState>(NO_FILTERS)
  const [offset, setOffset] = useState(0)
  const users = useUsers(toUserFilters(filters), offset)
  const teams = useTeamOptions()
  const setActive = useSetUserActive()
  const createReset = useCreatePasswordReset()

  const [editing, setEditing] = useState<AdminUser | null>(null)
  const [toggling, setToggling] = useState<AdminUser | null>(null)
  const [resetFor, setResetFor] = useState<AdminUser | null>(null)
  const [resetUrl, setResetUrl] = useState<string | null>(null)

  function changeFilters(next: FilterState) {
    setFilters(next)
    setOffset(0)
  }

  function confirmToggle() {
    if (!toggling) return
    const active = !toggling.is_active
    setActive.mutate(
      { id: toggling.id, active },
      {
        onSuccess: (user) => {
          toast.success(
            active ? `${user.username} reactivated` : `${user.username} deactivated and signed out`,
          )
          setToggling(null)
        },
        onError: (error) => {
          toast.error(errorMessage(error))
          setToggling(null)
        },
      },
    )
  }

  function generateReset(user: AdminUser) {
    createReset.mutate(user.id, {
      onSuccess: (created) => {
        setResetFor(user)
        setResetUrl(created.reset_url)
      },
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  const columns: Column<AdminUser>[] = [
    {
      key: 'user',
      header: 'User',
      isTitle: true,
      cell: (user) => (
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 font-semibold">
            {user.username}
            {user.id === me?.id && <span className="badge badge-sm badge-neutral">You</span>}
          </div>
          <div className="text-sm font-normal break-all text-base-content/80">{user.email}</div>
        </div>
      ),
    },
    { key: 'role', header: 'Role', cell: (user) => <RoleBadge role={user.role} /> },
    { key: 'team', header: 'Team', cell: (user) => user.team?.name ?? '—' },
    {
      key: 'status',
      header: 'Status',
      cell: (user) =>
        user.is_active ? (
          <span className="badge badge-sm badge-success">Active</span>
        ) : (
          <span className="badge badge-sm badge-neutral">Inactive</span>
        ),
    },
    { key: 'signin', header: 'Sign-in', cell: signInMethods },
    {
      key: 'created',
      header: 'Joined',
      cell: (user) => formatDateTime(user.created_at),
      className: 'whitespace-nowrap',
    },
    {
      key: 'actions',
      header: 'Actions',
      hideLabelOnCard: true,
      className: 'md:text-right',
      cell: (user) => {
        const isSelf = user.id === me?.id
        return (
          <div className="flex flex-wrap gap-2 md:flex-nowrap md:justify-end">
            {/* Your own role and team are fixed: admins have no team and cannot self-demote. */}
            {!isSelf && (
              <button type="button" className="btn btn-sm" onClick={() => setEditing(user)}>
                <PencilIcon className="size-4" />
                Edit
              </button>
            )}
            <button
              type="button"
              className="btn btn-sm"
              disabled={!user.is_active || createReset.isPending}
              title={user.is_active ? undefined : 'Reactivate the user first'}
              onClick={() => generateReset(user)}
            >
              <KeyIcon className="size-4" />
              Reset link
            </button>
            {!isSelf && (
              <button
                type="button"
                className={`btn btn-sm ${user.is_active ? 'btn-ghost' : 'btn-success'}`}
                onClick={() => setToggling(user)}
              >
                {user.is_active ? 'Deactivate' : 'Activate'}
              </button>
            )}
          </div>
        )
      },
    },
  ]

  return (
    <>
      <h2 className="mb-4 text-lg font-semibold">Users</h2>
      <Filters value={filters} teams={teams.data ?? []} onChange={changeFilters} />

      <DataTable
        caption="Users"
        columns={columns}
        rows={users.data?.items}
        rowKey={(user) => user.id}
        isLoading={users.isPending}
        error={users.error}
        onRetry={() => void users.refetch()}
        empty={
          <EmptyState
            icon={<UsersIcon className="size-6" />}
            title="No users match"
            description="Try other filters, or invite someone from the Invites tab."
          />
        }
      />
      {users.data && (
        <Pagination
          total={users.data.total}
          limit={users.data.limit}
          offset={users.data.offset}
          onChange={setOffset}
        />
      )}

      <Modal
        open={editing !== null}
        title={editing ? `Edit ${editing.username}` : 'Edit user'}
        onClose={() => setEditing(null)}
      >
        {editing && (
          <EditUserBody user={editing} teams={teams.data ?? []} onDone={() => setEditing(null)} />
        )}
      </Modal>

      <ConfirmModal
        open={toggling !== null}
        title={toggling?.is_active ? 'Deactivate user?' : 'Activate user?'}
        confirmLabel={toggling?.is_active ? 'Deactivate' : 'Activate'}
        tone={toggling?.is_active ? 'error' : 'primary'}
        isPending={setActive.isPending}
        onConfirm={confirmToggle}
        onCancel={() => setToggling(null)}
      >
        {toggling?.is_active ? (
          <p>
            <strong>{toggling.username}</strong> will be signed out everywhere immediately and
            cannot log in until reactivated. Their data is kept.
          </p>
        ) : (
          <p>
            <strong>{toggling?.username}</strong> will be able to log in again.
          </p>
        )}
      </ConfirmModal>

      <CopyLinkModal
        url={resetUrl}
        title="Password reset link"
        onClose={() => {
          setResetUrl(null)
          setResetFor(null)
        }}
      >
        Send this link to <strong>{resetFor?.username}</strong>. Using it sets a new password and
        signs them out everywhere.
      </CopyLinkModal>
    </>
  )
}
