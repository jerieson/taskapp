/*
 * The current user's personal dashboard. Every number is the caller's own and is
 * computed on the server. Log and task mutations invalidate `dashboardKeys.all`.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { api, type Schemas } from './client'

export type HoursPerDay = Schemas['HoursPerDay']
export type HoursPerWeek = Schemas['HoursPerWeek']
export type HoursByProject = Schemas['HoursByProject']
export type HoursByCategory = Schemas['HoursByCategory']
export type TaskCounts = Schemas['TaskCounts']

/** Inclusive calendar dates, "YYYY-MM-DD". */
export interface DateRange {
  from: string
  to: string
}

export const dashboardKeys = {
  all: ['dashboard'] as const,
  daily: (week: string) => ['dashboard', 'daily', week] as const,
  weekly: ['dashboard', 'weekly'] as const,
  byProject: (r: DateRange) => ['dashboard', 'by-project', r.from, r.to] as const,
  byCategory: (r: DateRange) => ['dashboard', 'by-category', r.from, r.to] as const,
  tasks: (r: DateRange) => ['dashboard', 'tasks', r.from, r.to] as const,
}

const rangeQuery = (r: DateRange) => ({ date_from: r.from, date_to: r.to })

/** `week` is that week's Monday. */
export function useHoursPerDay(week: string) {
  return useQuery({
    queryKey: dashboardKeys.daily(week),
    queryFn: () => api.get<HoursPerDay>('/dashboard/hours/daily', { query: { week } }),
    placeholderData: keepPreviousData,
  })
}

export function useHoursPerWeek() {
  return useQuery({
    queryKey: dashboardKeys.weekly,
    queryFn: () => api.get<HoursPerWeek>('/dashboard/hours/weekly'),
  })
}

export function useHoursByProject(range: DateRange) {
  return useQuery({
    queryKey: dashboardKeys.byProject(range),
    queryFn: () =>
      api.get<HoursByProject>('/dashboard/hours/by-project', { query: rangeQuery(range) }),
    placeholderData: keepPreviousData,
  })
}

export function useHoursByCategory(range: DateRange) {
  return useQuery({
    queryKey: dashboardKeys.byCategory(range),
    queryFn: () =>
      api.get<HoursByCategory>('/dashboard/hours/by-category', { query: rangeQuery(range) }),
    placeholderData: keepPreviousData,
  })
}

export function useTaskCounts(range: DateRange) {
  return useQuery({
    queryKey: dashboardKeys.tasks(range),
    queryFn: () => api.get<TaskCounts>('/dashboard/tasks', { query: rangeQuery(range) }),
    placeholderData: keepPreviousData,
  })
}
