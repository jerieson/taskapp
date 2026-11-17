/*
 * The body of a team dashboard: hours over time for the team and per member, hours by
 * member / project / category and task counts per member for a date range. Used by
 * /team/dashboard and the admin Overview tab. Week and range live in the URL.
 *
 * Hours follow the team snapshot on each log; task numbers are counts only.
 */
import { useState, type ReactNode } from 'react'

import {
  useTeamHoursByCategory,
  useTeamHoursByMember,
  useTeamHoursByProject,
  useTeamHoursPerDay,
  useTeamHoursPerWeek,
  useTeamTaskCounts,
  type TeamTaskCounts,
} from '../../api/dashboard'
import AsyncState from '../../components/AsyncState'
import DataTable, { type Column } from '../../components/DataTable'
import DateRangePicker from '../../components/DateRangePicker'
import EmptyState from '../../components/EmptyState'
import { UsersIcon } from '../../components/icons'
import { SkeletonChart } from '../../components/Skeleton'
import { useDateRangeParam, useWeekParam } from '../../lib/dateRange'
import {
  formatDay,
  formatDayWithWeekday,
  formatHours,
  formatShortDay,
  formatWeekday,
} from '../../lib/format'
import { memberNote } from '../../lib/labels'
import { ChartCard, NoHours, SectionTitle, WeekNav } from './ChartParts'
import HoursBarChart from './HoursBarChart'
import HoursPerDayChart from './HoursPerDayChart'
import HoursPerWeekChart from './HoursPerWeekChart'
import { MemberHoursTable, MemberName, OverdueBadge } from './MemberTable'

type View = 'team' | 'members'

/** "Team" (chart) or "Members" (table) for the hours-over-time cards. */
function ViewToggle({
  label,
  value,
  onChange,
}: {
  label: string
  value: View
  onChange: (view: View) => void
}) {
  const options: { value: View; label: string }[] = [
    { value: 'team', label: 'Team' },
    { value: 'members', label: 'Members' },
  ]
  return (
    <div className="join" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={`btn join-item btn-sm ${value === option.value ? 'btn-primary' : ''}`}
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

function Toolbar({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center justify-between gap-2">{children}</div>
}

const chartSkeleton = <div className="skeleton h-56 w-full" />

function HoursPerDayCard({ teamId }: { teamId: number }) {
  const [week, setWeek] = useWeekParam()
  const [view, setView] = useState<View>('team')
  const daily = useTeamHoursPerDay(teamId, week)
  return (
    <ChartCard
      title="Hours per day"
      aside={daily.data && `Total ${formatHours(daily.data.total)}`}
      toolbar={
        <Toolbar>
          <WeekNav week={week} onChange={setWeek} />
          <ViewToggle label="Hours per day view" value={view} onChange={setView} />
        </Toolbar>
      }
    >
      <AsyncState
        query={daily}
        isEmpty={daily.data?.total === 0}
        skeleton={chartSkeleton}
        empty={<NoHours title="No hours logged this week" />}
      >
        {() => {
          const data = daily.data!
          return view === 'team' ? (
            <HoursPerDayChart data={data} />
          ) : (
            <MemberHoursTable
              caption="Hours per day by member"
              columns={data.days.map((d) => ({
                key: d.date,
                label: formatWeekday(d.date),
                title: formatDayWithWeekday(d.date),
              }))}
              rows={data.members.map((m) => ({
                member: m.member,
                hours: m.days.map((d) => d.hours),
                total: m.total,
              }))}
              totals={data.days.map((d) => d.hours)}
            />
          )
        }}
      </AsyncState>
    </ChartCard>
  )
}

function HoursPerWeekCard({ teamId }: { teamId: number }) {
  const [view, setView] = useState<View>('team')
  const weekly = useTeamHoursPerWeek(teamId)
  return (
    <ChartCard
      title="Hours per week"
      aside="Last 8 weeks"
      toolbar={
        <Toolbar>
          <span />
          <ViewToggle label="Hours per week view" value={view} onChange={setView} />
        </Toolbar>
      }
    >
      <AsyncState
        query={weekly}
        isEmpty={weekly.data?.weeks.every((w) => w.hours === 0)}
        skeleton={chartSkeleton}
        empty={<NoHours title="No hours logged in the last 8 weeks" />}
      >
        {() => {
          const data = weekly.data!
          return view === 'team' ? (
            <HoursPerWeekChart data={data} />
          ) : (
            <MemberHoursTable
              caption="Hours per week by member"
              columns={data.weeks.map((w) => ({
                key: w.week_start,
                label: formatShortDay(w.week_start),
                title: `Week of ${formatDay(w.week_start)}`,
              }))}
              rows={data.members.map((m) => ({
                member: m.member,
                hours: m.weeks.map((w) => w.hours),
                total: m.total,
              }))}
              totals={data.weeks.map((w) => w.hours)}
            />
          )
        }}
      </AsyncState>
    </ChartCard>
  )
}

type MemberCounts = TeamTaskCounts['items'][number]

const TASK_COLUMNS: Column<MemberCounts>[] = [
  {
    key: 'member',
    header: 'Member',
    isTitle: true,
    cell: (row) => <MemberName member={row.member} />,
  },
  {
    key: 'completed',
    header: 'Completed in range',
    className: 'text-right tabular-nums',
    cell: (row) => row.completed,
  },
  {
    key: 'open',
    header: 'Open now',
    className: 'text-right tabular-nums',
    cell: (row) => row.open,
  },
  {
    key: 'overdue',
    header: 'Overdue',
    className: 'text-right tabular-nums',
    cell: (row) => (
      <span className="inline-flex items-center justify-end gap-2">
        {row.overdue > 0 && <OverdueBadge />}
        {row.overdue}
      </span>
    ),
  },
]

export default function TeamDashboard({ teamId }: { teamId: number }) {
  const rangeState = useDateRangeParam()
  const { range } = rangeState
  const byMember = useTeamHoursByMember(teamId, range)
  const byProject = useTeamHoursByProject(teamId, range)
  const byCategory = useTeamHoursByCategory(teamId, range)
  const tasks = useTeamTaskCounts(teamId, range)

  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="team-time" className="flex flex-col gap-4">
        <SectionTitle id="team-time">Hours over time</SectionTitle>
        <div className="grid gap-4 xl:grid-cols-2">
          <HoursPerDayCard teamId={teamId} />
          <HoursPerWeekCard teamId={teamId} />
        </div>
      </section>

      <section aria-labelledby="team-range" className="flex flex-col gap-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <SectionTitle id="team-range">By date range</SectionTitle>
          <DateRangePicker state={rangeState} />
        </div>

        <div className="grid gap-4 md:grid-cols-2 md:items-start">
          <AsyncState query={byMember} skeleton={<SkeletonChart />}>
            {() => (
              <ChartCard
                title="Hours by member"
                aside={`Total ${formatHours(byMember.data!.total)}`}
              >
                {byMember.data!.total === 0 ? (
                  <NoHours title="No hours in this range" />
                ) : (
                  <HoursBarChart
                    caption="Hours by member"
                    items={byMember.data!.items.map((item) => ({
                      key: String(item.member.id),
                      label: item.member.username,
                      note: memberNote(item.member),
                      hours: item.hours,
                    }))}
                  />
                )}
              </ChartCard>
            )}
          </AsyncState>

          <ChartCard title="Tasks per member" aside="Counts only">
            <DataTable
              caption="Task counts per member"
              columns={TASK_COLUMNS}
              rows={tasks.data?.items}
              rowKey={(row) => row.member.id}
              isLoading={tasks.isPending}
              error={tasks.error}
              onRetry={() => void tasks.refetch()}
              empty={
                <EmptyState
                  size="compact"
                  icon={<UsersIcon />}
                  title="No active members in this team"
                />
              }
            />
          </ChartCard>

          <AsyncState query={byProject} skeleton={<SkeletonChart />}>
            {() => (
              <ChartCard
                title="Hours by project"
                aside={`Total ${formatHours(byProject.data!.total)}`}
              >
                {byProject.data!.items.length === 0 ? (
                  <NoHours title="No hours in this range" />
                ) : (
                  <HoursBarChart
                    caption="Hours by project"
                    items={byProject.data!.items.map((item) => ({
                      key: item.project ? String(item.project.id) : 'none',
                      label: item.project?.name ?? 'No project',
                      note: item.project && !item.project.is_active ? 'inactive' : undefined,
                      hours: item.hours,
                    }))}
                  />
                )}
              </ChartCard>
            )}
          </AsyncState>

          <AsyncState query={byCategory} skeleton={<SkeletonChart />}>
            {() => (
              <ChartCard
                title="Hours by category"
                aside={`Total ${formatHours(byCategory.data!.total)}`}
              >
                {byCategory.data!.items.length === 0 ? (
                  <NoHours title="No hours in this range" />
                ) : (
                  <HoursBarChart
                    caption="Hours by category"
                    items={byCategory.data!.items.map((item) => ({
                      key: String(item.category.id),
                      label: item.category.label,
                      note: item.category.is_active ? undefined : 'inactive',
                      hours: item.hours,
                    }))}
                  />
                )}
              </ChartCard>
            )}
          </AsyncState>
        </div>
      </section>
    </div>
  )
}
