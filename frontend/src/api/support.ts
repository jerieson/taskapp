/*
 * Support dictionary: shared entries everyone reads and adds; the author or an admin
 * edits and (de)activates them. Plus the admin CSV import.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type Schemas } from './client'

export type SupportEntry = Schemas['SupportEntryOut']
export type SupportEntryCreate = Schemas['SupportEntryCreate']
export type SupportEntryUpdate = Schemas['SupportEntryUpdate']
export type SupportFacets = Schemas['SupportFacets']
export type SupportImport = Schemas['SupportImportOut']

export const SUPPORT_PAGE_SIZE = 20

export interface SupportFilters {
  q?: string
  type_id?: number
  project?: string
  module?: string
  include_inactive?: boolean
}

export const supportKeys = {
  all: ['support'] as const,
  list: (filters: SupportFilters, offset: number) => ['support', 'list', filters, offset] as const,
  detail: (id: number) => ['support', 'detail', id] as const,
  facets: ['support', 'facets'] as const,
}

export function useSupportEntries(filters: SupportFilters, offset: number) {
  return useQuery({
    queryKey: supportKeys.list(filters, offset),
    queryFn: () =>
      api.get<Schemas['Page_SupportEntryOut_']>('/support', {
        query: { ...filters, limit: SUPPORT_PAGE_SIZE, offset },
      }),
    placeholderData: keepPreviousData,
  })
}

export function useSupportEntry(id: number) {
  return useQuery({
    queryKey: supportKeys.detail(id),
    queryFn: () => api.get<SupportEntry>(`/support/${id}`),
  })
}

/** Distinct projects, modules and sub-modules in use, for filters and suggestions. */
export function useSupportFacets() {
  return useQuery({
    queryKey: supportKeys.facets,
    queryFn: () => api.get<SupportFacets>('/support/facets'),
    staleTime: 60 * 1000,
  })
}

function useInvalidateSupport() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: supportKeys.all })
}

export function useCreateSupportEntry() {
  const invalidate = useInvalidateSupport()
  return useMutation({
    mutationFn: (data: SupportEntryCreate) => api.post<SupportEntry>('/support', data),
    onSuccess: invalidate,
  })
}

export function useUpdateSupportEntry() {
  const invalidate = useInvalidateSupport()
  return useMutation({
    mutationFn: ({ id, ...data }: SupportEntryUpdate & { id: number }) =>
      api.patch<SupportEntry>(`/support/${id}`, data),
    onSuccess: invalidate,
  })
}

export function useSetSupportEntryActive() {
  const invalidate = useInvalidateSupport()
  return useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      api.post<SupportEntry>(`/support/${id}/${active ? 'activate' : 'deactivate'}`),
    onSuccess: invalidate,
  })
}

/** Upload the team's support sheet (CSV). `dryRun` previews the counts and saves nothing. */
export function useImportSupport() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ file, dryRun }: { file: File; dryRun: boolean }) => {
      const form = new FormData()
      form.append('file', file)
      return api.post<SupportImport>('/admin/support/import', form, {
        query: { dry_run: dryRun || undefined },
      })
    },
    onSuccess: (result) =>
      result.dry_run
        ? undefined
        : Promise.all([
            queryClient.invalidateQueries({ queryKey: supportKeys.all }),
            queryClient.invalidateQueries({ queryKey: ['lookups', 'support-types'] }),
          ]),
  })
}
