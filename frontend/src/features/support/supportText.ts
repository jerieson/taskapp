import type { SupportEntry } from '../../api/support'

/** "Project › Module › Sub-module" (blank parts left out). */
export function placeOf(entry: SupportEntry): string {
  return [entry.project, entry.module, entry.sub_module].filter(Boolean).join(' › ')
}
