import type { ReactNode } from 'react'

interface StatCardProps {
  label: string
  value: number
  hint?: ReactNode
  icon: ReactNode
  /** Under the hint, e.g. a "Needs attention" badge. */
  badge?: ReactNode
}

/** A headline number in a card (dashboards, admin overview). */
export default function StatCard({ label, value, hint, icon, badge }: StatCardProps) {
  return (
    <div className="card card-border border-base-300 bg-base-100">
      <div className="card-body flex-row items-start gap-3 p-4">
        <span className="rounded-field bg-base-200 p-2 text-base-content" aria-hidden="true">
          {icon}
        </span>
        <div className="min-w-0">
          <p className="text-sm text-base-content/80">{label}</p>
          <p className="text-3xl font-bold tabular-nums">{value}</p>
          {hint && <p className="text-xs text-base-content/80">{hint}</p>}
          {badge}
        </div>
      </div>
    </div>
  )
}
