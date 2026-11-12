import EmptyState from '../../components/EmptyState'
import { ChartIcon } from '../../components/icons'

/** Filled in by the admin dashboard phase. */
export default function OverviewTab() {
  return (
    <EmptyState
      icon={<ChartIcon className="size-6" />}
      title="Overview coming soon"
      description="Team dashboards, counts and AI usage will appear here."
    />
  )
}
