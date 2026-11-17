/*
 * /team/dashboard: managers see their own team; admins pick any team. Hours are
 * counted by the team a log was written in, so they stay with that team after
 * someone moves. The backend enforces access (devs never reach this page).
 */
import { useCurrentUser } from '../../api/auth'
import PageHeader from '../../components/PageHeader'
import AdminTeamDashboard from './AdminTeamDashboard'
import TeamDashboard from './TeamDashboard'

export default function TeamDashboardPage() {
  const me = useCurrentUser().data
  if (!me) return null
  if (me.role === 'admin') {
    return (
      <>
        <PageHeader
          title="Team dashboard"
          description="Hours by team, as recorded when they were logged, and task counts per member."
        />
        <AdminTeamDashboard />
      </>
    )
  }
  return (
    <>
      <PageHeader
        title="Team dashboard"
        description={
          <>
            Hours logged in <strong>{me.team?.name}</strong>, including by people who have since
            moved to another team, and task counts per current member.
          </>
        }
      />
      {me.team && <TeamDashboard teamId={me.team.id} />}
    </>
  )
}
