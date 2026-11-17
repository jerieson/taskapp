/*
 * Admin overview: headline counts, AI usage per user (last 30 days), and the team
 * dashboard with a team selector.
 */
import { useState } from 'react'
import { Link } from 'react-router'

import { useAdminOverview, useAIUsage, type AIUsageRow } from '../../api/admin'
import AsyncState from '../../components/AsyncState'
import DataTable, { type Column } from '../../components/DataTable'
import EmptyState from '../../components/EmptyState'
import { InboxIcon, StarIcon, UserIcon, UsersIcon } from '../../components/icons'
import Pagination from '../../components/Pagination'
import { SkeletonStat } from '../../components/Skeleton'
import StatCard from '../../components/StatCard'
import AdminTeamDashboard from '../dashboard/AdminTeamDashboard'
import { SectionTitle } from '../dashboard/ChartParts'

const numberFormat = new Intl.NumberFormat()
const formatCount = (n: number) => numberFormat.format(n)

function Counts() {
  const overview = useAdminOverview()
  return (
    <AsyncState
      query={overview}
      skeleton={
        <div className="grid gap-4 sm:grid-cols-3">
          <SkeletonStat />
          <SkeletonStat />
          <SkeletonStat />
        </div>
      }
    >
      {() => {
        const { users, teams, pending_invites } = overview.data!
        return (
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard
              label="Active users"
              value={users.active}
              icon={<UserIcon />}
              hint={
                <>
                  {users.admins} admin · {users.managers} manager · {users.devs} dev
                  {users.inactive > 0 && <> · {users.inactive} deactivated</>}
                </>
              }
            />
            <StatCard
              label="Teams"
              value={teams}
              icon={<UsersIcon />}
              hint={
                <Link to="?tab=teams" className="link">
                  Manage teams
                </Link>
              }
            />
            <StatCard
              label="Pending invites"
              value={pending_invites}
              icon={<InboxIcon />}
              hint={
                <Link to="?tab=invites" className="link">
                  {pending_invites > 0 ? 'Not accepted yet' : 'Invite someone'}
                </Link>
              }
            />
          </div>
        )
      }}
    </AsyncState>
  )
}

const AI_COLUMNS: Column<AIUsageRow>[] = [
  {
    key: 'user',
    header: 'User',
    isTitle: true,
    cell: (row) => (
      <span className="break-words">
        {row.user.username}
        {!row.is_active && (
          <span className="ml-1 text-xs font-normal text-base-content/80">(deactivated)</span>
        )}
      </span>
    ),
  },
  {
    key: 'requests',
    header: 'Requests',
    className: 'text-right tabular-nums',
    cell: (row) => formatCount(row.requests),
  },
  {
    key: 'failed',
    header: 'Failed',
    className: 'text-right tabular-nums',
    cell: (row) => formatCount(row.failed),
  },
  {
    key: 'input',
    header: 'Input tokens',
    className: 'text-right tabular-nums',
    cell: (row) => formatCount(row.input_tokens),
  },
  {
    key: 'output',
    header: 'Output tokens',
    className: 'text-right tabular-nums',
    cell: (row) => formatCount(row.output_tokens),
  },
]

function AIUsage() {
  const [offset, setOffset] = useState(0)
  const usage = useAIUsage(offset)
  return (
    <>
      <DataTable
        caption="AI usage per user, last 30 days"
        columns={AI_COLUMNS}
        rows={usage.data?.items}
        rowKey={(row) => row.user.id}
        isLoading={usage.isPending}
        error={usage.error}
        onRetry={() => void usage.refetch()}
        empty={
          <EmptyState
            size="compact"
            icon={<StarIcon />}
            title="No AI requests in the last 30 days"
            description="Usage appears here once people use the AI features."
          />
        }
      />
      {usage.data && (
        <Pagination
          total={usage.data.total}
          limit={usage.data.limit}
          offset={usage.data.offset}
          onChange={setOffset}
        />
      )}
    </>
  )
}

export default function OverviewTab() {
  return (
    <div className="flex flex-col gap-8">
      <Counts />
      <section aria-labelledby="overview-ai" className="flex flex-col gap-4">
        <div>
          <SectionTitle id="overview-ai">AI usage</SectionTitle>
          <p className="text-sm text-base-content/80">Per user, last 30 days.</p>
        </div>
        <AIUsage />
      </section>
      <section aria-labelledby="overview-team" className="flex flex-col gap-4">
        <SectionTitle id="overview-team">Team dashboard</SectionTitle>
        <AdminTeamDashboard />
      </section>
    </div>
  )
}
