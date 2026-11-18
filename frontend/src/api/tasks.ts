/*
 * The current user's own tasks.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type Schemas } from './client'

export type Task = Schemas['TaskOut']
export type TaskCreate = Schemas['TaskCreate']
export type TaskUpdate = Schemas['TaskUpdate']
export type TaskSort = Schemas['TaskSort']
export type TaskState = Schemas['TaskState']

export interface TaskFilters {
  state?: TaskState
  status_id?: number
  priority_id?: number
  project_id?: number
  category_id?: number
  due_from?: string
  due_to?: string
}

export const TASK_PAGE_SIZE = 50

export const taskKeys = {
  all: ['tasks'] as const,
  page: (filters: TaskFilters, sort: TaskSort, offset: number) =>
    ['tasks', 'page', filters, sort, offset] as const,
}

export function useTasks(filters: TaskFilters, sort: TaskSort, offset: number) {
  return useQuery({
    queryKey: taskKeys.page(filters, sort, offset),
    queryFn: () =>
      api.get<Schemas['Page_TaskOut_']>('/tasks', {
        query: { ...filters, sort, limit: TASK_PAGE_SIZE, offset },
      }),
    placeholderData: keepPreviousData,
  })
}

/**
 * The user's tasks for selects (up to the API maximum per page): open tasks by due
 * date, or with `openOnly = false` every task, newest first.
 */
export function useTaskOptions(openOnly = true) {
  return useQuery({
    queryKey: [...taskKeys.all, 'options', { openOnly }] as const,
    queryFn: () =>
      api.get<Schemas['Page_TaskOut_']>('/tasks', {
        query: openOnly
          ? { state: 'open', sort: 'due_date', limit: 200 }
          : { sort: '-created_at', limit: 200 },
      }),
    select: (page) => page.items,
  })
}

/** The dashboard counts tasks, so it is refreshed with the task lists. */
function useInvalidateTasks() {
  const queryClient = useQueryClient()
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: taskKeys.all }),
      queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
    ])
}

export function useCreateTask() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: (data: TaskCreate) => api.post<Task>('/tasks', data),
    onSuccess: invalidate,
  })
}

export function useUpdateTask() {
  const invalidate = useInvalidateTasks()
  return useMutation({
    mutationFn: ({ id, ...data }: TaskUpdate & { id: number }) =>
      api.patch<Task>(`/tasks/${id}`, data),
    onSuccess: invalidate,
  })
}

export function useDeleteTask() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete(`/tasks/${id}`),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: taskKeys.all }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
      ]),
  })
}
