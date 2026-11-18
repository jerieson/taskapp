/* Weekly planning helpers: the ticking clock, the open/locked check and copy summaries. */
import { useEffect, useState } from 'react'

import type { CopyResult } from '../../api/logs'
import { formatWeekday } from '../../lib/format'

/** The current time, refreshed every 30 seconds. */
export function useNow(): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(timer)
  }, [])
  return now
}

/** Whether the week is still open, also after the deadline passes while the page is open. */
export function useWeekOpen(week: { is_open: boolean; deadline: string } | undefined): boolean {
  const now = useNow()
  return week !== undefined && week.is_open && now < Date.parse(week.deadline)
}

const SKIP_REASON: Record<string, string> = {
  daily_hours_exceeded: 'would pass 24 planned hours',
  nothing_to_copy: 'nothing to copy',
}

/** A one-line summary of a copy, e.g. "Copied 6 rows. Skipped Tue (would pass…)." */
export function copySummary(result: CopyResult): string {
  const parts = [`Copied ${result.created} ${result.created === 1 ? 'row' : 'rows'}.`]
  const skipped = result.days.filter(
    (d) => d.skipped_reason && d.skipped_reason !== 'nothing_to_copy',
  )
  if (skipped.length) {
    const days = skipped
      .map((d) => `${formatWeekday(d.date)} (${SKIP_REASON[d.skipped_reason ?? ''] ?? ''})`)
      .join(', ')
    parts.push(`Skipped ${days}.`)
  }
  if (result.skipped_rows) {
    parts.push(
      `${result.skipped_rows} ${result.skipped_rows === 1 ? 'row was' : 'rows were'} left out (inactive or unlinked values).`,
    )
  }
  return parts.join(' ')
}
