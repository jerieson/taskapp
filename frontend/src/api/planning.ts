/*
 * Weekly planning status: the current user's planned hours per day for a week, the
 * Friday deadline and the reminder flag; and a team's status (managers: own team,
 * admins: any team). Log mutations invalidate `planningKeys.all`.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { api, type Schemas } from './client'

export type PlanningStatus = Schemas['PlanningStatus']
export type TeamPlanningStatus = Schemas['TeamPlanningStatus']

export const planningKeys = {
  all: ['planning'] as const,
  own: (week: string) => ['planning', 'own', week] as const,
  team: (teamId: number, week: string) => ['planning', 'team', teamId, week] as const,
}

/** `week`: any date in the week; omitted = next week. */
export function usePlanningStatus(week?: string, enabled = true) {
  return useQuery({
    queryKey: planningKeys.own(week ?? 'next'),
    queryFn: () => api.get<PlanningStatus>('/planning/status', { query: week ? { week } : {} }),
    placeholderData: keepPreviousData,
    enabled,
  })
}

export function useTeamPlanningStatus(teamId: number, week?: string) {
  return useQuery({
    queryKey: planningKeys.team(teamId, week ?? 'next'),
    queryFn: () =>
      api.get<TeamPlanningStatus>(`/teams/${teamId}/planning/status`, {
        query: week ? { week } : {},
      }),
    placeholderData: keepPreviousData,
  })
}
