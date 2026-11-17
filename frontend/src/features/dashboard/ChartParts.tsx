/*
 * Building blocks shared by the dashboards: section titles, the card frame, week
 * navigation, the hover tooltip, empty states, and a screen-reader table with the
 * same numbers as the chart.
 */
import type { ReactNode } from 'react'

import EmptyState from '../../components/EmptyState'
import { ChartIcon, ChevronLeftIcon, ChevronRightIcon } from '../../components/icons'
import { formatDayRange, mondayOf, shiftDay, todayIso } from '../../lib/format'

export function SectionTitle({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h2 id={id} className="text-lg font-semibold">
      {children}
    </h2>
  )
}

export function NoHours({ title }: { title: string }) {
  return <EmptyState size="compact" icon={<ChartIcon />} title={title} />
}

/** Previous / next week buttons; `week` is a Monday. */
export function WeekNav({ week, onChange }: { week: string; onChange: (monday: string) => void }) {
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

interface ChartCardProps {
  title: string
  /** Shown on the right of the title, e.g. the total. */
  aside?: ReactNode
  /** Controls under the title (e.g. week navigation). */
  toolbar?: ReactNode
  children: ReactNode
}

export function ChartCard({ title, aside, toolbar, children }: ChartCardProps) {
  return (
    <section className="card card-border min-w-0 border-base-300 bg-base-100">
      <div className="card-body gap-3 p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <h3 className="card-title text-base">{title}</h3>
          {aside && <div className="text-sm text-base-content/80 tabular-nums">{aside}</div>}
        </div>
        {toolbar}
        {children}
      </div>
    </section>
  )
}

export function ChartTooltip({ title, value }: { title: ReactNode; value: ReactNode }) {
  return (
    <div className="rounded-box border border-base-300 bg-base-100 px-3 py-2 text-sm text-base-content shadow-md">
      <div className="font-medium">{title}</div>
      <div className="text-base-content/80 tabular-nums">{value}</div>
    </div>
  )
}

/** The chart's numbers as a table, for screen readers. */
export function ChartTable({
  caption,
  columns,
  rows,
}: {
  caption: string
  columns: [string, string]
  rows: { key: string; label: string; value: string }[]
}) {
  return (
    <table className="sr-only">
      <caption>{caption}</caption>
      <thead>
        <tr>
          <th scope="col">{columns[0]}</th>
          <th scope="col">{columns[1]}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key}>
            <th scope="row">{row.label}</th>
            <td>{row.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
