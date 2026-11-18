/*
 * Prod logs: the current user's own logs, and the read-only team view (managers: own
 * team; admins: any team, and they can edit or delete through the normal endpoints).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type Schemas } from './client'

export type ProdLog = Schemas['ProdLogOut']
export type ProdLogItem = Schemas['ProdLogListItem']
export type ProdLogCreate = Schemas['ProdLogCreate']
export type ProdLogUpdate = Schemas['ProdLogUpdate']
export type TeamMember = Schemas['TeamMemberOut']

interface CommonFilters {
  date_from?: string
  date_to?: string
  project_id?: number
  category_id?: number
  activity_id?: number
}

export interface LogFilters extends CommonFilters {
  task_id?: number
}

export interface TeamLogFilters extends CommonFilters {
  user_id?: number
}

export const LOG_PAGE_SIZE = 50
const ALL = 200

export const logKeys = {
  all: ['logs'] as const,
  page: (filters: LogFilters, offset: number) => ['logs', 'own', filters, offset] as const,
  team: (teamId: number, filters: TeamLogFilters, offset: number) =>
    ['logs', 'team', teamId, filters, offset] as const,
  members: (teamId: number) => ['logs', 'members', teamId] as const,
}

export function useLogs(filters: LogFilters, offset: number) {
  return useQuery({
    queryKey: logKeys.page(filters, offset),
    queryFn: () =>
      api.get<Schemas['Page_ProdLogListItem_']>('/logs', {
        query: { ...filters, limit: LOG_PAGE_SIZE, offset },
      }),
    placeholderData: keepPreviousData,
  })
}

/** Every own log in a date range (a day or a week), without paging. */
export function useLogsInRange(from: string, to: string, enabled = true) {
  return useQuery({
    enabled,
    queryKey: logKeys.page({ date_from: from, date_to: to }, -1),
    queryFn: () =>
      api.get<Schemas['Page_ProdLogListItem_']>('/logs', {
        query: { date_from: from, date_to: to, limit: ALL },
      }),
    select: (page) => page.items,
  })
}

export function useTeamLogs(teamId: number | undefined, filters: TeamLogFilters, offset: number) {
  return useQuery({
    queryKey: logKeys.team(teamId ?? 0, filters, offset),
    queryFn: () =>
      api.get<Schemas['Page_ProdLogListItem_']>(`/teams/${teamId}/logs`, {
        query: { ...filters, limit: LOG_PAGE_SIZE, offset },
      }),
    enabled: teamId !== undefined,
    placeholderData: keepPreviousData,
  })
}

/** Current members plus former members with logs under the team (for the filter). */
export function useTeamMembers(teamId: number | undefined) {
  return useQuery({
    queryKey: logKeys.members(teamId ?? 0),
    queryFn: () =>
      api.get<Schemas['Page_TeamMemberOut_']>(`/teams/${teamId}/members`, {
        query: { limit: ALL },
      }),
    enabled: teamId !== undefined,
    select: (page) => page.items,
  })
}

function useInvalidateLogs() {
  const queryClient = useQueryClient()
  // The dashboard's hour charts and the planning status are computed from logs.
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: logKeys.all }),
      queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      queryClient.invalidateQueries({ queryKey: ['planning'] }),
    ])
}

export function useCreateLog() {
  const invalidate = useInvalidateLogs()
  return useMutation({
    mutationFn: (data: ProdLogCreate) => api.post<ProdLog>('/logs', data),
    onSuccess: invalidate,
  })
}

export function useUpdateLog() {
  const invalidate = useInvalidateLogs()
  return useMutation({
    mutationFn: ({ id, ...data }: ProdLogUpdate & { id: number }) =>
      api.patch<ProdLog>(`/logs/${id}`, data),
    onSuccess: invalidate,
  })
}

export type CopyLogs = Schemas['CopyLogs']
export type CopyResult = Schemas['CopyResult']

/** Copy a day's or a week's rows into days of an open week, as planned rows. */
export function useCopyLogs() {
  const invalidate = useInvalidateLogs()
  return useMutation({
    mutationFn: (data: CopyLogs) => api.post<CopyResult>('/logs/copy', data),
    onSuccess: invalidate,
  })
}

export function useDeleteLog() {
  const invalidate = useInvalidateLogs()
  return useMutation({
    mutationFn: (id: number) => api.delete(`/logs/${id}`),
    onSuccess: invalidate,
  })
}
