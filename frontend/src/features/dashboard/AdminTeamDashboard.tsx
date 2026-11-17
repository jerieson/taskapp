/*
 * Admins: a team selector (kept in `?team=`) above the team dashboard. Used by
 * /team/dashboard and the admin Overview tab.
 */
import { useSearchParams } from 'react-router'

import { useTeamOptions } from '../../api/admin'
import AsyncState from '../../components/AsyncState'
import EmptyState from '../../components/EmptyState'
import { SelectField } from '../../components/FormField'
import { UsersIcon } from '../../components/icons'
import { SkeletonForm } from '../../components/Skeleton'
import TeamDashboard from './TeamDashboard'

export default function AdminTeamDashboard() {
  const teams = useTeamOptions()
  const [params, setParams] = useSearchParams()
  const raw = Number(params.get('team'))
  const teamId = teams.data?.some((t) => t.id === raw) ? raw : teams.data?.[0]?.id

  function choose(id: number) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('team', String(id))
        return next
      },
      { replace: true },
    )
  }

  return (
    <AsyncState
      query={teams}
      isEmpty={teams.data?.length === 0}
      skeleton={<SkeletonForm fields={1} />}
      empty={
        <EmptyState
          icon={<UsersIcon className="size-6" />}
          title="No teams yet"
          description="Create a team under Admin to see its dashboard here."
        />
      }
    >
      {() => (
        <>
          <SelectField
            label="Team"
            wrapperClassName="mb-6 max-w-sm"
            value={teamId ?? ''}
            onChange={(event) => choose(Number(event.target.value))}
          >
            {teams.data?.map((team) => (
              <option key={team.id} value={team.id}>
                {team.name}
              </option>
            ))}
          </SelectField>
          {teamId !== undefined && <TeamDashboard key={teamId} teamId={teamId} />}
        </>
      )}
    </AsyncState>
  )
}
