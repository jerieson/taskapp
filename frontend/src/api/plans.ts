/*
 * Daily plans: the current user's own ordered list of open tasks for a date.
 *
 * Viewing a date does not create a plan: `usePlan` returns null until the first task
 * is added, which creates it (POST /plans is get-or-create).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, api, type Schemas } from './client'

export type Plan = Schemas['DailyPlanOut']
export type PlanItem = Schemas['PlanItemOut']

export const planKeys = {
  all: ['plans'] as const,
  date: (planDate: string) => ['plans', planDate] as const,
}

/** The plan for a date, or null when none has been created yet. */
export function usePlan(planDate: string) {
  return useQuery({
    queryKey: planKeys.date(planDate),
    queryFn: async (): Promise<Plan | null> => {
      try {
        return await api.get<Plan>(`/plans/by-date/${planDate}`)
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
  })
}

/** Mutations return the whole plan; store it directly instead of refetching. */
function usePlanMutation<V>(planDate: string, fn: (vars: V) => Promise<Plan>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (plan) => queryClient.setQueryData(planKeys.date(planDate), plan),
  })
}

export interface AddItemVars {
  /** null when the date has no plan yet: it is created first. */
  planId: number | null
  task_id: number
  suggested_hours?: number | null
}

export function useAddPlanItem(planDate: string) {
  return usePlanMutation(planDate, async ({ planId, ...body }: AddItemVars) => {
    const id = planId ?? (await api.post<Plan>('/plans', { plan_date: planDate })).id
    return api.post<Plan>(`/plans/${id}/items`, body)
  })
}

export function useUpdatePlanItem(planDate: string) {
  return usePlanMutation(
    planDate,
    ({ planId, itemId, hours }: { planId: number; itemId: number; hours: number | null }) =>
      api.patch<Plan>(`/plans/${planId}/items/${itemId}`, { suggested_hours: hours }),
  )
}

export function useReorderPlan(planDate: string) {
  return usePlanMutation(planDate, ({ planId, itemIds }: { planId: number; itemIds: number[] }) =>
    api.put<Plan>(`/plans/${planId}/order`, { item_ids: itemIds }),
  )
}

export function useRemovePlanItem(planDate: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ planId, itemId }: { planId: number; itemId: number }) =>
      api.delete(`/plans/${planId}/items/${itemId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: planKeys.date(planDate) }),
  })
}
