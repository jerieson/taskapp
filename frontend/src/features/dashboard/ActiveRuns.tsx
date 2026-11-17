import { Link } from 'react-router'

import { useActiveRuns } from '../../api/processes'
import AsyncState from '../../components/AsyncState'
import EmptyState from '../../components/EmptyState'
import { RepeatIcon } from '../../components/icons'
import { SkeletonCard } from '../../components/Skeleton'
import { formatDate } from '../../lib/format'
import { RunProgressBar } from '../processes/RunBits'

/** The caller's runs in progress, each with a done / total progress bar. */
export default function ActiveRuns() {
  const runs = useActiveRuns()
  return (
    <AsyncState
      query={runs}
      isEmpty={runs.data?.total === 0}
      skeleton={<SkeletonCard lines={3} />}
      empty={
        <div className="card card-border border-base-300 bg-base-100">
          <EmptyState
            size="compact"
            icon={<RepeatIcon />}
            title="No runs in progress"
            description="Start a run from one of your processes to track it here."
            action={
              <Link to="/processes" className="btn btn-primary btn-sm">
                Go to processes
              </Link>
            }
          />
        </div>
      }
    >
      {() => {
        const page = runs.data!
        return (
          <div className="card card-border border-base-300 bg-base-100">
            <ul className="divide-y divide-base-300">
              {page.items.map((run) => (
                <li key={run.id} className="flex flex-col gap-2 p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                    <Link
                      to={`/runs/${run.id}`}
                      className="link font-medium link-hover break-words"
                    >
                      {run.process.name}
                    </Link>
                    <span className="text-xs text-base-content/80">
                      Started {formatDate(run.started_at)}
                    </span>
                  </div>
                  <RunProgressBar run={run} label={`${run.process.name} progress`} />
                </li>
              ))}
            </ul>
            {page.total > page.items.length && (
              <p className="border-t border-base-300 px-4 py-3 text-sm text-base-content/80">
                Showing {page.items.length} of {page.total} runs in progress.
              </p>
            )}
          </div>
        )
      }}
    </AsyncState>
  )
}
