/*
 * /dashboard: the user's own numbers. Hours per day (one week, `?week=` Monday) and per
 * week (last 8 weeks), actual with planned alongside; hours by project, category and
 * activity plus task counts for a shared
 * date range (`?range=` / `?from=&to=`).
 */
import {
  useHoursByActivity,
  useHoursByCategory,
  useHoursByProject,
  useHoursPerDay,
  useHoursPerWeek,
  useTaskCounts,
} from '../../api/dashboard'
import AsyncState from '../../components/AsyncState'
import DateRangePicker from '../../components/DateRangePicker'
import PageHeader from '../../components/PageHeader'
import { SkeletonChart, SkeletonStat } from '../../components/Skeleton'
import { useDateRangeParam, useWeekParam } from '../../lib/dateRange'
import { formatHours } from '../../lib/format'
import { ChartCard, NoHours, SectionTitle, WeekNav } from './ChartParts'
import HoursBarChart from './HoursBarChart'
import HoursPerDayChart from './HoursPerDayChart'
import HoursPerWeekChart from './HoursPerWeekChart'
import TaskStats from './TaskStats'

export default function DashboardPage() {
  const [week, setWeek] = useWeekParam()
  const rangeState = useDateRangeParam()
  const { range } = rangeState

  const daily = useHoursPerDay(week)
  const weekly = useHoursPerWeek()
  const byProject = useHoursByProject(range)
  const byCategory = useHoursByCategory(range)
  const byActivity = useHoursByActivity(range)
  const counts = useTaskCounts(range)

  return (
    <>
      <PageHeader title="Dashboard" description="Your own hours and tasks." />

      <div className="flex flex-col gap-8">
        <section aria-labelledby="dash-time" className="flex flex-col gap-4">
          <SectionTitle id="dash-time">Hours over time</SectionTitle>
          <div className="grid gap-4 md:grid-cols-2">
            <ChartCard
              title="Hours per day"
              aside={daily.data && `Total ${formatHours(daily.data.total)}`}
              toolbar={<WeekNav week={week} onChange={setWeek} />}
            >
              <AsyncState
                query={daily}
                isEmpty={daily.data?.total === 0}
                skeleton={<div className="skeleton h-56 w-full" />}
                empty={<NoHours title="No hours logged this week" />}
              >
                {() => <HoursPerDayChart data={daily.data!} />}
              </AsyncState>
            </ChartCard>
            <ChartCard title="Hours per week" aside="Last 8 weeks">
              <AsyncState
                query={weekly}
                isEmpty={weekly.data?.weeks.every((w) => w.hours === 0)}
                skeleton={<div className="skeleton h-56 w-full" />}
                empty={<NoHours title="No hours logged in the last 8 weeks" />}
              >
                {() => <HoursPerWeekChart data={weekly.data!} />}
              </AsyncState>
            </ChartCard>
          </div>
        </section>

        <section aria-labelledby="dash-range" className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <SectionTitle id="dash-range">By date range</SectionTitle>
            <DateRangePicker state={rangeState} />
          </div>

          <AsyncState
            query={counts}
            skeleton={
              <div className="grid gap-4 sm:grid-cols-3">
                <SkeletonStat />
                <SkeletonStat />
                <SkeletonStat />
              </div>
            }
          >
            {() => <TaskStats counts={counts.data!} />}
          </AsyncState>

          <div className="grid gap-4 md:grid-cols-2 md:items-start">
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
            <AsyncState query={byActivity} skeleton={<SkeletonChart />}>
              {() => (
                <ChartCard
                  title="Hours by activity"
                  aside={`Total ${formatHours(byActivity.data!.total)}`}
                >
                  {byActivity.data!.items.length === 0 ? (
                    <NoHours title="No hours in this range" />
                  ) : (
                    <HoursBarChart
                      caption="Hours by activity"
                      items={byActivity.data!.items.map((item) => ({
                        key: String(item.activity.id),
                        label: item.activity.label,
                        note: item.activity.is_active ? undefined : 'inactive',
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
    </>
  )
}
