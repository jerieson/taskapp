/*
 * Building blocks shared by the dashboard charts: the card frame, the hover tooltip,
 * and a screen-reader table with the same numbers as the chart.
 */
import type { ReactNode } from 'react'

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
