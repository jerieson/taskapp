import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, ApiError, type Schemas } from './client'

export type CurrentUser = Schemas['MeOut']
export type Role = Schemas['Role']

export const authKeys = {
  me: ['auth', 'me'] as const,
  invite: (token: string) => ['auth', 'invite', token] as const,
  reset: (token: string) => ['auth', 'reset', token] as const,
}

async function fetchCurrentUser(): Promise<CurrentUser | null> {
  try {
    return await api.get<CurrentUser>('/auth/me', { skipAuthRedirect: true })
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

/** The logged-in user, or null when logged out. */
export function useCurrentUser() {
  return useQuery({ queryKey: authKeys.me, queryFn: fetchCurrentUser })
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: Schemas['LoginIn']) =>
      api.post<CurrentUser>('/auth/login', data, { skipAuthRedirect: true }),
    onSuccess: (user) => {
      queryClient.removeQueries()
      queryClient.setQueryData(authKeys.me, user)
    },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/auth/logout', undefined, { skipAuthRedirect: true }),
    // Even if the call fails, the user wanted out: drop all cached data.
    onSettled: () => {
      queryClient.removeQueries()
      queryClient.setQueryData(authKeys.me, null)
    },
  })
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (data: Schemas['ChangePasswordIn']) => api.post('/auth/change-password', data),
  })
}

export function useInvite(token: string) {
  return useQuery({
    queryKey: authKeys.invite(token),
    queryFn: () => api.get<Schemas['InvitePublicOut']>(`/invites/${encodeURIComponent(token)}`),
  })
}

export function useAcceptInvite(token: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: Schemas['InviteAcceptIn']) =>
      api.post<CurrentUser>(`/invites/${encodeURIComponent(token)}/accept`, data),
    onSuccess: (user) => {
      queryClient.removeQueries()
      queryClient.setQueryData(authKeys.me, user)
    },
  })
}

export function usePasswordResetCheck(token: string) {
  return useQuery({
    queryKey: authKeys.reset(token),
    queryFn: () =>
      api.get<Schemas['PasswordResetCheck']>(`/password-resets/${encodeURIComponent(token)}`),
  })
}

export function useResetPassword(token: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: Schemas['PasswordResetIn']) =>
      api.post(`/password-resets/${encodeURIComponent(token)}`, data),
    // All of that user's sessions are revoked; if it was this browser's user, it is
    // now logged out.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: authKeys.me }),
  })
}

/** Google sign-in is a full-page redirect, not a fetch. */
export function googleLoginUrl(inviteToken?: string): string {
  return inviteToken
    ? `/api/auth/google/login?invite=${encodeURIComponent(inviteToken)}`
    : '/api/auth/google/login'
}
