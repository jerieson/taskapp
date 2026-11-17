/*
 * /dashboard: the user's own numbers. Hours per day (one week, `?week=` Monday) and per
 * week (last 8 weeks); hours by project and category plus task counts for a shared
 * date range (`?range=` / `?from=&to=`); process runs in progress.
 */
import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router'

import {
  useHoursByCategory,
  useHoursByProject,
  useHoursPerDay,
  useHoursPerWeek,
  useTaskCounts,
} from '../../api/dashboard'
import AsyncState from '../../components/AsyncState'
import DateRangePicker from '../../components/DateRangePicker'
import EmptyState from '../../components/EmptyState'
import { ChartIcon, ChevronLeftIcon, ChevronRightIcon } from '../../components/icons'
import PageHeader from '../../components/PageHeader'
import { SkeletonChart, SkeletonStat } from '../../components/Skeleton'
import { useDateRangeParam } from '../../lib/dateRange'
import { formatDayRange, formatHours, mondayOf, shiftDay, todayIso } from '../../lib/format'
import ActiveRuns from './ActiveRuns'
import { ChartCard } from './ChartParts'
import HoursBarChart from './HoursBarChart'
import HoursPerDayChart from './HoursPerDayChart'
import HoursPerWeekChart from './HoursPerWeekChart'
import TaskStats from './TaskStats'

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

function useWeekParam(): [string, (monday: string) => void] {
  const [params, setParams] = useSearchParams()
  const raw = params.get('week')
  const current = mondayOf(todayIso())
  const week = raw && DATE_PATTERN.test(raw) ? mondayOf(raw) : current
  const setWeek = (monday: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (monday === current) next.delete('week')
        else next.set('week', monday)
        return next
      },
      { replace: true },
    )
  return [week, setWeek]
}

function SectionTitle({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h2 id={id} className="text-lg font-semibold">
      {children}
    </h2>
  )
}

function noHours(title: string) {
  return <EmptyState size="compact" icon={<ChartIcon />} title={title} />
}

function WeekNav({ week, onChange }: { week: string; onChange: (monday: string) => void }) {
  const current = mondayOf(todayIso())
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="join">
        <button
          type="button"
          className="btn join-item btn-square btn-sm"
          onClick={() => onChange(shiftDay(week, -7))}
          aria-label="Previous week"
        >
          <ChevronLeftIcon />
        </button>
        <button
          type="button"
          className="btn join-item btn-square btn-sm"
          onClick={() => onChange(shiftDay(week, 7))}
          aria-label="Next week"
        >
          <ChevronRightIcon />
        </button>
      </div>
      <span className="text-sm" aria-live="polite">
        {formatDayRange(week, shiftDay(week, 6))}
      </span>
      {week !== current && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange(current)}>
          This week
        </button>
      )}
    </div>
  )
}

export default function DashboardPage() {
  const [week, setWeek] = useWeekParam()
  const rangeState = useDateRangeParam()
  const { range } = rangeState

  const daily = useHoursPerDay(week)
  const weekly = useHoursPerWeek()
  const byProject = useHoursByProject(range)
  const byCategory = useHoursByCategory(range)
  const counts = useTaskCounts(range)

  return (
    <>
      <PageHeader title="Dashboard" description="Your own hours, tasks and process runs." />

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
                empty={noHours('No hours logged this week')}
              >
                {() => <HoursPerDayChart data={daily.data!} />}
              </AsyncState>
            </ChartCard>
            <ChartCard title="Hours per week" aside="Last 8 weeks">
              <AsyncState
                query={weekly}
                isEmpty={weekly.data?.weeks.every((w) => w.hours === 0)}
                skeleton={<div className="skeleton h-56 w-full" />}
                empty={noHours('No hours logged in the last 8 weeks')}
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
                    noHours('No hours in this range')
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
                    noHours('No hours in this range')
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

        <section aria-labelledby="dash-runs" className="flex flex-col gap-4">
          <SectionTitle id="dash-runs">Active process runs</SectionTitle>
          <ActiveRuns />
        </section>
      </div>
    </>
  )
}
