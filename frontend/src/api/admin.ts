import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type Schemas } from './client'

export type Team = Schemas['TeamOut']
export type AdminUser = Schemas['AdminUserOut']
export type Invite = Schemas['InviteOut']
export type InviteCreated = Schemas['InviteCreated']
export type InviteStatus = Schemas['InviteStatus']
export type PasswordResetCreated = Schemas['PasswordResetCreated']

export interface UserFilters {
  team_id?: number
  role?: Schemas['Role']
  is_active?: boolean
}

export const PAGE_SIZE = 50
/** Enough for every team in a dropdown (the API maximum). */
const ALL = 200

export const adminKeys = {
  all: ['admin'] as const,
  teams: ['admin', 'teams'] as const,
  teamPage: (offset: number) => ['admin', 'teams', 'page', offset] as const,
  teamOptions: ['admin', 'teams', 'options'] as const,
  users: ['admin', 'users'] as const,
  userPage: (filters: UserFilters, offset: number) =>
    ['admin', 'users', 'page', filters, offset] as const,
  invites: ['admin', 'invites'] as const,
  invitePage: (offset: number) => ['admin', 'invites', 'page', offset] as const,
}

// ------------------------------------------------------------------ teams

export function useTeams(offset: number) {
  return useQuery({
    queryKey: adminKeys.teamPage(offset),
    queryFn: () =>
      api.get<Schemas['Page_TeamOut_']>('/admin/teams', { query: { limit: PAGE_SIZE, offset } }),
    placeholderData: keepPreviousData,
  })
}

/** All teams, for selects and for showing team names. */
export function useTeamOptions() {
  return useQuery({
    queryKey: adminKeys.teamOptions,
    queryFn: () => api.get<Schemas['Page_TeamOut_']>('/admin/teams', { query: { limit: ALL } }),
    select: (page) => page.items,
  })
}

/** Team changes affect member counts, team names on users and invites. */
function useInvalidateAdmin() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: adminKeys.all })
}

export function useCreateTeam() {
  const invalidate = useInvalidateAdmin()
  return useMutation({
    mutationFn: (data: Schemas['TeamIn']) => api.post<Team>('/admin/teams', data),
    onSuccess: invalidate,
  })
}

export function useRenameTeam() {
  const invalidate = useInvalidateAdmin()
  return useMutation({
    mutationFn: ({ id, ...data }: Schemas['TeamIn'] & { id: number }) =>
      api.patch<Team>(`/admin/teams/${id}`, data),
    onSuccess: invalidate,
  })
}

export function useDeleteTeam() {
  const invalidate = useInvalidateAdmin()
  return useMutation({
    mutationFn: (id: number) => api.delete(`/admin/teams/${id}`),
    onSuccess: invalidate,
  })
}

// ------------------------------------------------------------------ users

export function useUsers(filters: UserFilters, offset: number) {
  return useQuery({
    queryKey: adminKeys.userPage(filters, offset),
    queryFn: () =>
      api.get<Schemas['Page_AdminUserOut_']>('/admin/users', {
        query: { ...filters, limit: PAGE_SIZE, offset },
      }),
    placeholderData: keepPreviousData,
  })
}

export function useUpdateUser() {
  const invalidate = useInvalidateAdmin()
  return useMutation({
    mutationFn: ({ id, ...data }: Schemas['AdminUserUpdate'] & { id: number }) =>
      api.patch<AdminUser>(`/admin/users/${id}`, data),
    onSuccess: invalidate,
  })
}

export function useSetUserActive() {
  const invalidate = useInvalidateAdmin()
  return useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      api.post<AdminUser>(`/admin/users/${id}/${active ? 'activate' : 'deactivate'}`),
    onSuccess: invalidate,
  })
}

export function useCreatePasswordReset() {
  return useMutation({
    mutationFn: (id: number) => api.post<PasswordResetCreated>(`/admin/users/${id}/password-reset`),
  })
}

// ------------------------------------------------------------------ invites

export function useInvites(offset: number) {
  return useQuery({
    queryKey: adminKeys.invitePage(offset),
    queryFn: () =>
      api.get<Schemas['Page_InviteOut_']>('/admin/invites', {
        query: { limit: PAGE_SIZE, offset },
      }),
    placeholderData: keepPreviousData,
  })
}

export function useCreateInvite() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: Schemas['InviteCreate']) => api.post<InviteCreated>('/admin/invites', data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: adminKeys.invites }),
  })
}

/** A new link for a pending invite; the previous link stops working. */
export function useRegenerateInviteLink() {
  return useMutation({
    mutationFn: (id: number) => api.post<InviteCreated>(`/admin/invites/${id}/link`),
  })
}

export function useRevokeInvite() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete(`/admin/invites/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: adminKeys.invites }),
  })
}
