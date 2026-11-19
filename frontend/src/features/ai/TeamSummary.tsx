/*
 * AI team summary on the team dashboard. The period is the dashboard's date range.
 * Figures come from the database (stat cards); the AI only writes the narrative.
 * "Generate summary" returns the saved summary for the same team and period without
 * calling the AI; "Regenerate" always asks for a new one. Past summaries are listed
 * newest first and open in a modal.
 */
import { useState } from 'react'

import {
  TEAM_SUMMARY_PAGE_SIZE,
  useTeamSummaries,
  useTeamSummary,
  type TeamSummary,
  type TeamSummaryResult,
} from '../../api/ai'
import { ApiError } from '../../api/client'
import type { DateRange } from '../../api/dashboard'
import AsyncState from '../../components/AsyncState'
import EmptyState from '../../components/EmptyState'
import ErrorAlert from '../../components/ErrorAlert'
import {
  AlertIcon,
  CalendarIcon,
  ClockIcon,
  InboxIcon,
  ListIcon,
  SparklesIcon,
  UsersIcon,
} from '../../components/icons'
import Markdown from '../../components/Markdown'
import Modal from '../../components/Modal'
import Pagination from '../../components/Pagination'
import StatCard from '../../components/StatCard'
import { formatDateTime, formatDayRange, formatHours } from '../../lib/format'
import { ChartCard } from '../dashboard/ChartParts'

function SummaryMeta({ summary }: { summary: TeamSummary }) {
  return (
    <p className="text-sm text-base-content/80">
      Generated {formatDateTime(summary.created_at)} by {summary.requested_by.username} ·{' '}
      <span className="break-all">{summary.model}</span>
    </p>
  )
}

function StatCards({ stats }: { stats: TeamSummaryResult['stats'] }) {
  return (
    <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
      <StatCard label="Actual hours" value={formatHours(stats.actual_hours)} icon={<ClockIcon />} />
      <StatCard
        label="Planned hours"
        value={formatHours(stats.planned_hours)}
        icon={<CalendarIcon />}
      />
      <StatCard
        label="Unplanned hours"
        value={formatHours(stats.unplanned_hours)}
        hint="Actual hours on Unplanned rows"
        icon={<AlertIcon />}
      />
      <StatCard label="Members with hours" value={stats.members_with_hours} icon={<UsersIcon />} />
      <StatCard label="Log rows" value={stats.log_rows} icon={<ListIcon />} />
      <StatCard
        label="Rows with a deviation reason"
        value={stats.deviation_rows}
        icon={<InboxIcon />}
      />
    </div>
  )
}

/** Keyed by team and range by the parent, so a new period starts empty. */
export function TeamSummaryCard({ teamId, range }: { teamId: number; range: DateRange }) {
  const request = useTeamSummary()
  const history = useTeamSummaries(teamId)
  const result = request.data
  const hasSaved = history.data?.items.some(
    (s) => s.period_start === range.from && s.period_end === range.to,
  )
  const limitReached = request.error instanceof ApiError && request.error.status === 429

  function generate(regenerate: boolean) {
    request.mutate({ teamId, from: range.from, to: range.to, regenerate })
  }

  return (
    <ChartCard title="AI summary" aside={formatDayRange(range.from, range.to)}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-base-content/80">
          Log remarks for this period are sent to the AI provider. The AI writes the narrative; the
          figures come from the database.
        </p>
        {!result && (
          <button
            type="button"
            className="btn btn-primary shrink-0"
            disabled={request.isPending}
            onClick={() => generate(false)}
          >
            {request.isPending ? (
              <span className="loading loading-spinner loading-sm" />
            ) : (
              <SparklesIcon className="size-4" />
            )}
            {request.isPending
              ? 'Generating…'
              : hasSaved
                ? 'Show saved summary'
                : 'Generate summary'}
          </button>
        )}
      </div>

      {request.isError && (
        <ErrorAlert
          error={request.error}
          title={limitReached ? 'Daily AI limit reached' : 'Could not generate the summary'}
          onRetry={
            limitReached ? undefined : () => generate(request.variables?.regenerate ?? false)
          }
        />
      )}

      {result && (
        <div className="grid gap-4 xl:grid-cols-3 xl:items-start">
          <div className="flex min-w-0 flex-col gap-3 rounded-box bg-base-200 p-4 xl:col-span-2">
            <Markdown>{result.summary_text}</Markdown>
            <div className="flex flex-col gap-2 border-t border-base-300 pt-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-wrap items-center gap-2">
                <SummaryMeta summary={result} />
                {result.cached && <span className="badge badge-sm badge-outline">Saved</span>}
              </div>
              <button
                type="button"
                className="btn btn-sm shrink-0"
                disabled={request.isPending}
                onClick={() => generate(true)}
              >
                {request.isPending ? (
                  <span className="loading loading-spinner loading-xs" />
                ) : (
                  <SparklesIcon className="size-4" />
                )}
                {request.isPending ? 'Regenerating…' : 'Regenerate'}
              </button>
            </div>
          </div>
          <StatCards stats={result.stats} />
        </div>
      )}
    </ChartCard>
  )
}

export function PastSummaries({ teamId }: { teamId: number }) {
  const [offset, setOffset] = useState(0)
  const [open, setOpen] = useState<TeamSummary | null>(null)
  const page = useTeamSummaries(teamId, offset)

  return (
    <ChartCard title="Past AI summaries" aside={page.data && `${page.data.total} saved`}>
      <AsyncState
        query={page}
        isEmpty={page.data?.total === 0}
        skeleton={<div className="skeleton h-32 w-full" />}
        empty={
          <EmptyState
            size="compact"
            icon={<SparklesIcon />}
            title="No summaries yet"
            description="Generate one for a period above."
          />
        }
      >
        {() => (
          <>
            <ul className="divide-y divide-base-300">
              {page.data!.items.map((summary) => (
                <li
                  key={summary.id}
                  className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <p className="font-medium">
                      {formatDayRange(summary.period_start, summary.period_end)}
                    </p>
                    <SummaryMeta summary={summary} />
                  </div>
                  <button
                    type="button"
                    className="btn btn-sm shrink-0 self-start sm:self-auto"
                    onClick={() => setOpen(summary)}
                    aria-label={`View summary for ${formatDayRange(summary.period_start, summary.period_end)}, generated ${formatDateTime(summary.created_at)}`}
                  >
                    View
                  </button>
                </li>
              ))}
            </ul>
            <Pagination
              total={page.data!.total}
              limit={TEAM_SUMMARY_PAGE_SIZE}
              offset={offset}
              onChange={setOffset}
            />
          </>
        )}
      </AsyncState>

      <Modal
        open={open !== null}
        title={open ? `Summary: ${formatDayRange(open.period_start, open.period_end)}` : ''}
        wide
        onClose={() => setOpen(null)}
      >
        {open && (
          <div className="flex flex-col gap-3">
            <Markdown>{open.summary_text}</Markdown>
            <div className="border-t border-base-300 pt-3">
              <SummaryMeta summary={open} />
            </div>
          </div>
        )}
      </Modal>
    </ChartCard>
  )
}
