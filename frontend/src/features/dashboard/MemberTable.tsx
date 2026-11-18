/*
 * Team dashboard pieces that list members: a member's name with notes (former
 * member, deactivated), and a members-by-period hours table.
 */
import type { ReactNode } from 'react'

import type { DashboardMember } from '../../api/dashboard'
import { formatHours } from '../../lib/format'
import { memberNote } from '../../lib/labels'

export function MemberName({ member }: { member: DashboardMember }) {
  const note = memberNote(member)
  return (
    <span className="break-words">
      {member.username}
      {note && <span className="ml-1 text-xs font-normal text-base-content/80">({note})</span>}
    </span>
  )
}

export function OverdueBadge({ className = '' }: { className?: string }) {
  return (
    <span className={`badge badge-sm border-warning bg-warning text-warning-content ${className}`}>
      Needs attention
    </span>
  )
}

export interface PeriodColumn {
  key: string
  /** Short header, e.g. "Mon" or "Nov 10". */
  label: string
  /** Full name for screen readers and the tooltip, e.g. "Monday, Nov 10". */
  title: string
}

export interface MemberRow {
  member: DashboardMember
  /** Shown after the name, e.g. a "Not planned" badge. */
  badge?: ReactNode
  /** One value per column, in column order. */
  hours: number[]
  total: number
}

/** Members down the side, periods across; scrolls sideways inside its own box. */
export function MemberHoursTable({
  caption,
  columns,
  rows,
  totals,
}: {
  caption: string
  columns: PeriodColumn[]
  rows: MemberRow[]
  /** The team row at the bottom, one value per column. */
  totals: number[]
}) {
  const grandTotal = totals.reduce((sum, h) => sum + h, 0)
  return (
    <div className="overflow-x-auto rounded-box border border-base-300">
      <table className="table table-sm table-pin-cols tabular-nums">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Member</th>
            {columns.map((c) => (
              <td key={c.key} className="text-right" title={c.title}>
                <span aria-hidden="true">{c.label}</span>
                <span className="sr-only">{c.title}</span>
              </td>
            ))}
            <td className="text-right font-semibold">Total</td>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.member.id}>
              <th scope="row" className="max-w-36 font-normal">
                <MemberName member={row.member} />
                {row.badge && <div className="mt-1">{row.badge}</div>}
              </th>
              {columns.map((c, i) => {
                const h = row.hours[i] ?? 0
                return (
                  <td key={c.key} className="text-right">
                    {h === 0 ? <span className="text-base-content/60">–</span> : formatHours(h)}
                  </td>
                )
              })}
              <td className="text-right font-semibold">{formatHours(row.total)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Team</th>
            {columns.map((c, i) => (
              <td key={c.key} className="text-right">
                {formatHours(totals[i] ?? 0)}
              </td>
            ))}
            <td className="text-right">{formatHours(grandTotal)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}
