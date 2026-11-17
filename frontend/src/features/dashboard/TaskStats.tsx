import type { TaskCounts } from '../../api/dashboard'
import { AlertIcon, CheckCircleIcon, ListIcon } from '../../components/icons'
import StatCard from '../../components/StatCard'
import { OverdueBadge } from './MemberTable'

export default function TaskStats({ counts }: { counts: TaskCounts }) {
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <StatCard
        label="Completed"
        value={counts.completed}
        hint="Tasks finished in this range"
        icon={<CheckCircleIcon />}
      />
      <StatCard
        label="Open"
        value={counts.open}
        hint="Not done yet, right now"
        icon={<ListIcon />}
      />
      <StatCard
        label="Overdue"
        value={counts.overdue}
        hint="Open and past their due date"
        icon={<AlertIcon />}
        badge={counts.overdue > 0 && <OverdueBadge className="mt-2" />}
      />
    </div>
  )
}
