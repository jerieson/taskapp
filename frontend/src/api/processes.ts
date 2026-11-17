/*
 * The current user's own processes (step templates) and their runs.
 *
 * Starting a run creates tasks, and run progress follows task status changes, so
 * task mutations also invalidate `processKeys.all` and `runKeys.all` (see api/tasks).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type Schemas } from './client'

export type Process = Schemas['ProcessOut']
export type ProcessListItem = Schemas['ProcessListItem']
export type ProcessStep = Schemas['ProcessStepOut']
export type ProcessCreate = Schemas['ProcessCreate']
export type StepSync = Schemas['StepSync']
export type Run = Schemas['RunOut']
export type RunDetail = Schemas['RunDetail']
export type RunStatus = Schemas['RunStatus']

export const PROCESS_PAGE_SIZE = 50
export const RUN_PAGE_SIZE = 20

export const processKeys = {
  all: ['processes'] as const,
  list: (isActive: boolean, offset: number) => ['processes', 'list', isActive, offset] as const,
  detail: (id: number) => ['processes', 'detail', id] as const,
  runs: (id: number, offset: number) => ['processes', 'runs', id, offset] as const,
}

export const runKeys = {
  all: ['runs'] as const,
  detail: (id: number) => ['runs', id] as const,
  list: (status: RunStatus | null) => ['runs', 'list', status] as const,
}

export function useProcesses(isActive: boolean, offset: number) {
  return useQuery({
    queryKey: processKeys.list(isActive, offset),
    queryFn: () =>
      api.get<Schemas['Page_ProcessListItem_']>('/processes', {
        query: { is_active: isActive, limit: PROCESS_PAGE_SIZE, offset },
      }),
    placeholderData: keepPreviousData,
  })
}

export function useProcess(id: number) {
  return useQuery({
    queryKey: processKeys.detail(id),
    queryFn: () => api.get<Process>(`/processes/${id}`),
  })
}

export function useProcessRuns(id: number, offset: number) {
  return useQuery({
    queryKey: processKeys.runs(id, offset),
    queryFn: () =>
      api.get<Schemas['Page_RunOut_']>(`/processes/${id}/runs`, {
        query: { limit: RUN_PAGE_SIZE, offset },
      }),
    placeholderData: keepPreviousData,
  })
}

export function useRun(id: number) {
  return useQuery({
    queryKey: runKeys.detail(id),
    queryFn: () => api.get<RunDetail>(`/runs/${id}`),
  })
}

function useInvalidateProcesses() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: processKeys.all })
}

export function useCreateProcess() {
  const invalidate = useInvalidateProcesses()
  return useMutation({
    mutationFn: (data: ProcessCreate) => api.post<Process>('/processes', data),
    onSuccess: invalidate,
  })
}

export interface ProcessEdit {
  id: number
  name: string
  description: string | null
  steps: StepSync[]
}

/** Saves name/description, then the complete step list (one transaction each). */
export function useEditProcess() {
  const invalidate = useInvalidateProcesses()
  return useMutation({
    mutationFn: async ({ id, steps, ...fields }: ProcessEdit) => {
      await api.patch<Process>(`/processes/${id}`, fields)
      return api.put<Process>(`/processes/${id}/steps`, { steps })
    },
    // Invalidate even after a partial failure (the name may have been saved).
    onSettled: invalidate,
  })
}

export function useSetProcessActive() {
  const invalidate = useInvalidateProcesses()
  return useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      api.post<Process>(`/processes/${id}/${active ? 'activate' : 'deactivate'}`),
    onSuccess: invalidate,
  })
}

export function useDeleteProcess() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete(`/processes/${id}`),
    onSuccess: (_data, id) => {
      queryClient.removeQueries({ queryKey: processKeys.detail(id) })
      return queryClient.invalidateQueries({ queryKey: processKeys.all })
    },
  })
}

/** The new run's tasks show up in the task lists and the task picker. */
function useInvalidateRunChanges() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: processKeys.all }),
      queryClient.invalidateQueries({ queryKey: runKeys.all }),
      queryClient.invalidateQueries({ queryKey: ['tasks'] }),
    ])
}

export function useStartRun() {
  const invalidate = useInvalidateRunChanges()
  return useMutation({
    mutationFn: ({ processId, dueDate }: { processId: number; dueDate: string | null }) =>
      api.post<RunDetail>(`/processes/${processId}/runs`, { due_date: dueDate }),
    onSuccess: invalidate,
  })
}

export function useCancelRun() {
  const invalidate = useInvalidateRunChanges()
  return useMutation({
    mutationFn: (id: number) => api.post<RunDetail>(`/runs/${id}/cancel`),
    onSuccess: invalidate,
  })
}

export const ACTIVE_RUNS_LIMIT = 20

/** The caller's runs in progress, across all processes (dashboard widget). */
export function useActiveRuns() {
  return useQuery({
    queryKey: runKeys.list('in_progress'),
    queryFn: () =>
      api.get<Schemas['Page_RunOut_']>('/runs', {
        query: { status: 'in_progress', limit: ACTIVE_RUNS_LIMIT },
      }),
  })
}
