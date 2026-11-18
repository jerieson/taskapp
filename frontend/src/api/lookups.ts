/*
 * Dropdown values (categories, statuses, priorities, work set-ups, activities, activity
 * groups, O&M projects), projects, and the sheet's Data tab import.
 *
 * Every role can read active values; admins also manage them and see inactive ones.
 * Code never refers to a value by its label: use the `is_default` / `is_done` /
 * `requires_om_project` flags.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type Schemas } from './client'

export type Category = Schemas['CategoryOut']
export type Status = Schemas['StatusOut']
export type Priority = Schemas['PriorityOut']
export type WorkSetup = Schemas['WorkSetupOut']
export type Activity = Schemas['ActivityOut']
export type ActivityGroup = Schemas['ActivityGroupOut']
export type OmProject = Schemas['OmProjectOut']
export type Project = Schemas['ProjectOut']
export type DataTabImport = Schemas['DataTabImportOut']
export type LogOptions = Schemas['LogOptionsOut']
export type LogOptionProject = Schemas['LogOptionProject']

export type LookupKind =
  | 'categories'
  | 'statuses'
  | 'priorities'
  | 'work-setups'
  | 'activities'
  | 'activity-groups'
  | 'om-projects'
export type DefaultKind = 'statuses' | 'priorities' | 'work-setups'
export type LookupRow =
  Category | Status | Priority | WorkSetup | Activity | ActivityGroup | OmProject

interface LookupTypes {
  categories: {
    row: Category
    page: Schemas['Page_CategoryOut_']
    create: Schemas['CategoryCreate']
    update: Schemas['CategoryUpdate']
  }
  statuses: {
    row: Status
    page: Schemas['Page_StatusOut_']
    create: Schemas['StatusCreate']
    update: Schemas['StatusUpdate']
  }
  priorities: {
    row: Priority
    page: Schemas['Page_PriorityOut_']
    create: Schemas['LookupCreate']
    update: Schemas['LookupUpdate']
  }
  'work-setups': {
    row: WorkSetup
    page: Schemas['Page_WorkSetupOut_']
    create: Schemas['LookupCreate']
    update: Schemas['LookupUpdate']
  }
  activities: {
    row: Activity
    page: Schemas['Page_ActivityOut_']
    create: Schemas['LongLookupCreate']
    update: Schemas['LongLookupUpdate']
  }
  'activity-groups': {
    row: ActivityGroup
    page: Schemas['Page_ActivityGroupOut_']
    create: Schemas['PlainLookupCreate']
    update: Schemas['PlainLookupUpdate']
  }
  'om-projects': {
    row: OmProject
    page: Schemas['Page_OmProjectOut_']
    create: Schemas['OmProjectCreate']
    update: Schemas['OmProjectUpdate']
  }
}

export const PROJECT_PAGE_SIZE = 50
/** Enough for every value in a select (the API maximum). */
const ALL = 200

export const lookupKeys = {
  all: ['lookups'] as const,
  kind: (kind: LookupKind | 'projects') => ['lookups', kind] as const,
  list: (kind: LookupKind | 'projects', includeInactive: boolean) =>
    ['lookups', kind, { includeInactive }] as const,
  projectPage: (offset: number) => ['lookups', 'projects', 'page', offset] as const,
  logOptions: ['lookups', 'log-options'] as const,
}

// ------------------------------------------------------------------ dropdown values

/**
 * Every value of one dropdown, in display order. Admins can pass includeInactive;
 * everyone else gets active values only (the API rejects includeInactive for them).
 */
export function useLookups<K extends LookupKind>(kind: K, includeInactive = false) {
  return useQuery({
    queryKey: lookupKeys.list(kind, includeInactive),
    queryFn: () =>
      api.get<LookupTypes[K]['page']>(`/${kind}`, {
        query: { limit: ALL, include_inactive: includeInactive || undefined },
      }),
    select: (page): LookupTypes[K]['row'][] => page.items,
  })
}

function useInvalidate(kind: LookupKind | 'projects') {
  const queryClient = useQueryClient()
  // Every dropdown change can change what the log form offers.
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: lookupKeys.kind(kind) }),
      queryClient.invalidateQueries({ queryKey: lookupKeys.logOptions }),
    ])
}

export function useCreateLookup<K extends LookupKind>(kind: K) {
  const invalidate = useInvalidate(kind)
  return useMutation({
    mutationFn: (data: LookupTypes[K]['create']) =>
      api.post<LookupTypes[K]['row']>(`/${kind}`, data),
    onSuccess: invalidate,
  })
}

export function useUpdateLookup<K extends LookupKind>(kind: K) {
  const invalidate = useInvalidate(kind)
  return useMutation({
    mutationFn: ({ id, ...data }: LookupTypes[K]['update'] & { id: number }) =>
      api.patch<LookupTypes[K]['row']>(`/${kind}/${id}`, data),
    onSuccess: invalidate,
  })
}

export function useSetLookupActive(kind: LookupKind) {
  const invalidate = useInvalidate(kind)
  return useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      api.post<LookupRow>(`/${kind}/${id}/${active ? 'activate' : 'deactivate'}`),
    onSuccess: invalidate,
  })
}

/** Statuses, priorities and work set-ups only: the previous default loses the flag. */
export function useSetLookupDefault(kind: DefaultKind) {
  const invalidate = useInvalidate(kind)
  return useMutation({
    mutationFn: (id: number) => api.post<Status | Priority | WorkSetup>(`/${kind}/${id}/default`),
    onSuccess: invalidate,
  })
}

/** Replace an activity group's members with `activityIds`, in that order. */
export function useSetGroupActivities() {
  const invalidate = useInvalidate('activity-groups')
  return useMutation({
    mutationFn: ({ id, activityIds }: { id: number; activityIds: number[] }) =>
      api.put<ActivityGroup>(`/activity-groups/${id}/activities`, { activity_ids: activityIds }),
    onSuccess: invalidate,
  })
}

/** Upload the sheet's Data tab (CSV). Refreshes every dropdown list afterwards. */
export function useImportDataTab() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api.post<DataTabImport>('/admin/import/data-tab', form)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: lookupKeys.all }),
  })
}

/**
 * Save a new display order. `ids` must list every value (active and inactive).
 * The admin list updates immediately and rolls back if the request fails.
 */
export function useReorderLookups(kind: LookupKind) {
  const queryClient = useQueryClient()
  const key = lookupKeys.list(kind, true)
  return useMutation({
    mutationFn: (ids: number[]) => api.put(`/${kind}/order`, { ids }),
    onMutate: async (ids) => {
      await queryClient.cancelQueries({ queryKey: key })
      const previous = queryClient.getQueryData<{ items: LookupRow[] }>(key)
      if (previous) {
        const byId = new Map(previous.items.map((row) => [row.id, row]))
        const items = ids.flatMap((id, i) => {
          const row = byId.get(id)
          return row ? [{ ...row, sort_order: i + 1 }] : []
        })
        queryClient.setQueryData(key, { ...previous, items })
      }
      return { previous }
    },
    onError: (_error, _ids, context) => {
      if (context?.previous) queryClient.setQueryData(key, context.previous)
    },
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: lookupKeys.kind(kind) }),
        queryClient.invalidateQueries({ queryKey: lookupKeys.logOptions }),
      ]),
  })
}

// ------------------------------------------------------------------ log form options

/**
 * Everything the prod log form needs for its linked dropdowns (category -> projects ->
 * activities, O&M projects, work set-ups), active values only, in display order.
 */
export function useLogOptions() {
  return useQuery({
    queryKey: lookupKeys.logOptions,
    queryFn: () => api.get<LogOptions>('/log-options'),
    staleTime: 5 * 60 * 1000,
  })
}

// ------------------------------------------------------------------ projects

/** Admin list: active and inactive projects, paginated. */
export function useProjectPage(offset: number) {
  return useQuery({
    queryKey: lookupKeys.projectPage(offset),
    queryFn: () =>
      api.get<Schemas['Page_ProjectOut_']>('/projects', {
        query: { limit: PROJECT_PAGE_SIZE, offset, include_inactive: true },
      }),
    placeholderData: keepPreviousData,
  })
}

/** Active projects, for selects. */
export function useActiveProjects() {
  return useQuery({
    queryKey: lookupKeys.list('projects', false),
    queryFn: () => api.get<Schemas['Page_ProjectOut_']>('/projects', { query: { limit: ALL } }),
    select: (page) => page.items,
  })
}

export function useCreateProject() {
  const invalidate = useInvalidate('projects')
  return useMutation({
    mutationFn: (data: Schemas['ProjectCreate']) => api.post<Project>('/projects', data),
    onSuccess: invalidate,
  })
}

export function useUpdateProject() {
  const invalidate = useInvalidate('projects')
  return useMutation({
    mutationFn: ({ id, ...data }: Schemas['ProjectUpdate'] & { id: number }) =>
      api.patch<Project>(`/projects/${id}`, data),
    onSuccess: invalidate,
  })
}

export function useSetProjectActive() {
  const invalidate = useInvalidate('projects')
  return useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      api.post<Project>(`/projects/${id}/${active ? 'activate' : 'deactivate'}`),
    onSuccess: invalidate,
  })
}

// ------------------------------------------------------------------ select options

export type SelectKind = LookupKind | 'projects'

export interface SelectOption {
  id: number
  label: string
  color: string | null
  isActive: boolean
}

/** The value stored on an existing record (dropdown values have `label`, projects `name`). */
export type CurrentValue = { id: number } & ({ label: string } | { name: string })

type AnyPage = LookupTypes[LookupKind]['page'] | Schemas['Page_ProjectOut_']

function toOption(row: AnyPage['items'][number]): SelectOption {
  if ('name' in row) return { id: row.id, label: row.name, color: null, isActive: row.is_active }
  const color = 'color' in row ? row.color : null
  return { id: row.id, label: row.label, color, isActive: row.is_active }
}

/** Active options in display order, plus `current` if it is no longer active. */
export function useSelectOptions(kind: SelectKind, current?: CurrentValue | null) {
  const query = useQuery({
    queryKey: lookupKeys.list(kind, false),
    queryFn: () => api.get<AnyPage>(`/${kind}`, { query: { limit: ALL } }),
    select: (page) => page.items.map(toOption),
  })
  const active = query.data ?? []
  let options = active
  if (current && !active.some((option) => option.id === current.id)) {
    const label = 'label' in current ? current.label : current.name
    options = [...active, { id: current.id, label, color: null, isActive: false }]
  }
  return { options, isPending: query.isPending, error: query.error }
}
