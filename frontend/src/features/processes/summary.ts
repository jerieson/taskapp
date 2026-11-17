import type { ProcessListItem } from '../../api/processes'

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

/** "3 steps · 1 in progress · 4 runs" */
export function processSummary(process: ProcessListItem): string {
  const parts = [plural(process.step_count, 'step', 'steps')]
  if (process.active_run_count > 0) parts.push(`${process.active_run_count} in progress`)
  parts.push(plural(process.run_count, 'run', 'runs'))
  return parts.join(' · ')
}
