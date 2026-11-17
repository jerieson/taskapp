/*
 * Dropdown values (categories, statuses, priorities) and projects.
 *
 * Every role can read active values; admins also manage them and see inactive ones.
 * Code never refers to a value by its label: use the `is_default` / `is_done` flags.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type Schemas } from './client'

export type Category = Schemas['CategoryOut']
export type Status = Schemas['StatusOut']
export type Priority = Schemas['PriorityOut']
export type Project = Schemas['ProjectOut']

export type LookupKind = 'categories' | 'statuses' | 'priorities'
export type LookupRow = Category | Status | Priority

interface LookupTypes {
  categories: { row: Category; page: Schemas['Page_CategoryOut_']; create: Schemas['LookupCreate'] }
  statuses: { row: Status; page: Schemas['Page_StatusOut_']; create: Schemas['StatusCreate'] }
  priorities: {
    row: Priority
    page: Schemas['Page_PriorityOut_']
    create: Schemas['LookupCreate']
  }
}

type UpdateBody<K extends LookupKind> = K extends 'statuses'
  ? Schemas['StatusUpdate']
  : Schemas['LookupUpdate']

export const PROJECT_PAGE_SIZE = 50
/** Enough for every value in a select (the API maximum). */
const ALL = 200

export const lookupKeys = {
  all: ['lookups'] as const,
  kind: (kind: LookupKind | 'projects') => ['lookups', kind] as const,
  list: (kind: LookupKind | 'projects', includeInactive: boolean) =>
    ['lookups', kind, { includeInactive }] as const,
  projectPage: (offset: number) => ['lookups', 'projects', 'page', offset] as const,
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
  return () => queryClient.invalidateQueries({ queryKey: lookupKeys.kind(kind) })
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
    mutationFn: ({ id, ...data }: UpdateBody<K> & { id: number }) =>
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

/** Statuses and priorities only: the previous default loses the flag. */
export function useSetLookupDefault(kind: 'statuses' | 'priorities') {
  const invalidate = useInvalidate(kind)
  return useMutation({
    mutationFn: (id: number) => api.post<Status | Priority>(`/${kind}/${id}/default`),
    onSuccess: invalidate,
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
    onSettled: () => queryClient.invalidateQueries({ queryKey: lookupKeys.kind(kind) }),
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

type AnyPage =
  | Schemas['Page_CategoryOut_']
  | Schemas['Page_StatusOut_']
  | Schemas['Page_PriorityOut_']
  | Schemas['Page_ProjectOut_']

function toOption(row: AnyPage['items'][number]): SelectOption {
  if ('name' in row) return { id: row.id, label: row.name, color: null, isActive: row.is_active }
  return { id: row.id, label: row.label, color: row.color, isActive: row.is_active }
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
