/*
 * The prod log's linked dropdowns, mirroring the backend rules (app/services/prod_logs.py):
 * a project must be under the category, the activity must be in the project's activity
 * group, and "Project (For O&M)" is only offered when the category has
 * `requires_om_project`.
 *
 * Built from GET /api/log-options (active values only). Values ids are strings, as in
 * the form ("" = none).
 */
import type { Activity, Category, LogOptionProject, LogOptions } from '../../api/lookups'

export interface Choice {
  id: number
  label: string
  /** Set for a value already on the record that can no longer be chosen. */
  note?: 'inactive' | 'not linked'
}

/** A value stored on an existing log (it may be inactive or no longer linked). */
export type Current = { id: number; is_active: boolean } & ({ label: string } | { name: string })

export interface Linked {
  categories: Category[]
  category: (id: string) => Category | undefined
  project: (id: string) => LogOptionProject | undefined
  /** Projects under the category, by name. */
  projectsFor: (categoryId: string) => LogOptionProject[]
  /** Activities offered for the project, in the group's order. */
  activitiesFor: (projectId: string) => Activity[]
  offersOmProject: (categoryId: string) => boolean
  isProjectValid: (projectId: string, categoryId: string) => boolean
  isActivityValid: (activityId: string, projectId: string) => boolean
  defaultWorkSetupId: string
}

export function buildLinked(options: LogOptions): Linked {
  const categories = new Map(options.categories.map((c) => [String(c.id), c]))
  const projects = new Map(options.projects.map((p) => [String(p.id), p]))
  const activities = new Map(options.activities.map((a) => [a.id, a]))
  const groups = new Map(options.activity_groups.map((g) => [g.id, g.activity_ids]))

  const projectsFor = (categoryId: string) =>
    categoryId ? options.projects.filter((p) => p.category_ids.includes(Number(categoryId))) : []
  const activitiesFor = (projectId: string) => {
    const group = projects.get(projectId)?.activity_group_id
    const ids = group ? (groups.get(group) ?? []) : []
    return ids.flatMap((id) => activities.get(id) ?? [])
  }
  const defaultWorkSetup = options.work_setups.find((w) => w.is_default)

  return {
    categories: options.categories,
    category: (id) => categories.get(id),
    project: (id) => projects.get(id),
    projectsFor,
    activitiesFor,
    offersOmProject: (id) => categories.get(id)?.requires_om_project ?? false,
    isProjectValid: (projectId, categoryId) =>
      projectsFor(categoryId).some((p) => String(p.id) === projectId),
    isActivityValid: (activityId, projectId) =>
      activitiesFor(projectId).some((a) => String(a.id) === activityId),
    defaultWorkSetupId: defaultWorkSetup ? String(defaultWorkSetup.id) : '',
  }
}

/**
 * Active choices, plus the record's current value when `keep` is true and it is not
 * among them (inactive, or no longer linked to its parent). The backend accepts such a
 * value only while its parent is unchanged, so pass `keep` = "parent is unchanged".
 */
export function withCurrent(
  rows: { id: number; label?: string; name?: string }[],
  current: Current | null | undefined,
  keep = true,
): Choice[] {
  const choices: Choice[] = rows.map((row) => ({ id: row.id, label: row.label ?? row.name ?? '' }))
  if (keep && current && !choices.some((c) => c.id === current.id)) {
    const label = 'label' in current ? current.label : current.name
    choices.push({ id: current.id, label, note: current.is_active ? 'not linked' : 'inactive' })
  }
  return choices
}
