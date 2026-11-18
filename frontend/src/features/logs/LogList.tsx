/*
 * Prod logs grouped by date, each day with its actual and planned totals. Used by /logs
 * and /team/logs. The API sorts by date (newest first) and sends each day's totals
 * across all pages, so a day split over two pages still shows its full totals.
 */
import type { ReactNode } from 'react'

import type { ProdLogItem } from '../../api/logs'
import ColorDot from '../../components/ColorDot'
import { SkeletonCard } from '../../components/Skeleton'
import { formatDayWithWeekday, formatHours } from '../../lib/format'

interface DayGroup {
  date: string
  actual: number
  planned: number
  logs: ProdLogItem[]
}

function groupByDay(logs: ProdLogItem[]): DayGroup[] {
  const groups: DayGroup[] = []
  for (const log of logs) {
    const last = groups.at(-1)
    if (last?.date === log.log_date) last.logs.push(log)
    else
      groups.push({
        date: log.log_date,
        actual: log.day_total_hours,
        planned: log.day_planned_hours,
        logs: [log],
      })
  }
  return groups
}

interface LogListProps {
  logs: ProdLogItem[]
  /** Show who wrote each log (team view). */
  showAuthor?: boolean
  /** Screen-reader label for the day total, e.g. "Total" or "Team total". */
  totalLabel: string
  actions?: (log: ProdLogItem) => ReactNode
}

export default function LogList({ logs, showAuthor = false, totalLabel, actions }: LogListProps) {
  return (
    <div className="flex flex-col gap-4">
      {groupByDay(logs).map((group) => (
        <section
          key={group.date}
          aria-label={formatDayWithWeekday(group.date)}
          className="overflow-hidden rounded-box border border-base-300 bg-base-100"
        >
          <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-base-300 bg-base-200 px-4 py-2.5">
            <h2 className="font-semibold">{formatDayWithWeekday(group.date)}</h2>
            <span className="flex items-center gap-2 text-sm">
              {group.planned > 0 && (
                <span className="text-base-content/80 tabular-nums">
                  {formatHours(group.planned)} planned
                </span>
              )}
              <span className="badge badge-primary font-semibold tabular-nums">
                <span className="sr-only">{totalLabel} actual: </span>
                {formatHours(group.actual)}
              </span>
            </span>
          </header>
          <ul className="divide-y divide-base-300">
            {group.logs.map((log) => (
              <LogRow key={log.id} log={log} showAuthor={showAuthor} actions={actions?.(log)} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

function Hours({ log, className }: { log: ProdLogItem; className: string }) {
  return (
    <span className={`flex flex-col items-end leading-tight tabular-nums ${className}`}>
      <span className="font-semibold">
        {log.hours_spent === null ? (
          <span className="text-base-content/80">
            —<span className="sr-only">no actual hours yet</span>
          </span>
        ) : (
          formatHours(log.hours_spent)
        )}
      </span>
      {log.planned_hours !== null && (
        <span className="text-xs text-base-content/80">{formatHours(log.planned_hours)} plan</span>
      )}
    </span>
  )
}

function LogRow({
  log,
  showAuthor,
  actions,
}: {
  log: ProdLogItem
  showAuthor: boolean
  actions?: ReactNode
}) {
  const edited = log.updated_by.id !== log.user.id
  return (
    <li className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-start sm:gap-4">
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <p className="font-medium break-words">
            {showAuthor && <span className="font-semibold">{log.user.username}: </span>}
            <span className="inline-flex items-center gap-1.5">
              <ColorDot color={log.activity.color} />
              {log.activity.label}
            </span>
          </p>
          <Hours log={log} className="shrink-0 sm:hidden" />
        </div>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-base-content/80">
          {log.project && <span className="break-words">{log.project.name}</span>}
          <span className="inline-flex items-center gap-1.5">
            {log.project && <span aria-hidden="true">·</span>}
            <ColorDot color={log.category.color} />
            {log.category.label}
          </span>
          {log.om_project && <span className="break-words">· O&M: {log.om_project.label}</span>}
          {log.task && <span className="break-all">· Task: {log.task.title}</span>}
        </p>
        {log.title && <p className="mt-1 text-sm break-words">{log.title}</p>}
        {log.description && (
          <p className="mt-1 line-clamp-3 text-sm break-words whitespace-pre-line text-base-content/80">
            {log.description}
          </p>
        )}
        {log.deviation_reason && (
          <p className="mt-1 text-sm break-words whitespace-pre-line">
            <span className="font-medium">Deviation:</span> {log.deviation_reason}
          </p>
        )}
        <p className="mt-1.5 flex flex-wrap gap-1.5">
          <span className="badge badge-sm badge-outline">{log.work_setup.label}</span>
          {!log.is_planned && <span className="badge badge-sm badge-secondary">Unplanned</span>}
          {edited && (
            <span className="badge badge-sm badge-accent">edited by {log.updated_by.username}</span>
          )}
        </p>
      </div>
      <div className="flex items-center gap-2 sm:shrink-0">
        <Hours log={log} className="hidden w-20 sm:flex" />
        {actions}
      </div>
    </li>
  )
}

export function LogListSkeleton() {
  return (
    <div className="flex flex-col gap-4" aria-hidden="true">
      <SkeletonCard lines={3} />
      <SkeletonCard lines={2} />
    </div>
  )
}
