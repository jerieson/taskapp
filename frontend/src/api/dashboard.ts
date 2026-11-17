/*
 * Dashboards: the current user's own numbers, and team dashboards below. Everything
 * is computed on the server. Log and task mutations invalidate `dashboardKeys.all`.
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

// ------------------------------------------------------------------ team dashboard
// Managers: their own team; admins: any team. Keys sit under `dashboardKeys.all`, so
// log and task mutations refresh them too.

export type TeamHoursPerDay = Schemas['TeamHoursPerDay']
export type TeamHoursPerWeek = Schemas['TeamHoursPerWeek']
export type HoursByMember = Schemas['HoursByMember']
export type TeamTaskCounts = Schemas['TeamTaskCounts']
export type DashboardMember = Schemas['TeamMemberOut']

export const teamDashboardKeys = {
  all: (teamId: number) => ['dashboard', 'team', teamId] as const,
  daily: (teamId: number, week: string) => ['dashboard', 'team', teamId, 'daily', week] as const,
  weekly: (teamId: number) => ['dashboard', 'team', teamId, 'weekly'] as const,
  byMember: (teamId: number, r: DateRange) =>
    ['dashboard', 'team', teamId, 'by-member', r.from, r.to] as const,
  byProject: (teamId: number, r: DateRange) =>
    ['dashboard', 'team', teamId, 'by-project', r.from, r.to] as const,
  byCategory: (teamId: number, r: DateRange) =>
    ['dashboard', 'team', teamId, 'by-category', r.from, r.to] as const,
  tasks: (teamId: number, r: DateRange) =>
    ['dashboard', 'team', teamId, 'tasks', r.from, r.to] as const,
}

const teamPath = (teamId: number, path: string) => `/teams/${teamId}/dashboard/${path}`

export function useTeamHoursPerDay(teamId: number, week: string) {
  return useQuery({
    queryKey: teamDashboardKeys.daily(teamId, week),
    queryFn: () => api.get<TeamHoursPerDay>(teamPath(teamId, 'hours/daily'), { query: { week } }),
    placeholderData: keepPreviousData,
  })
}

export function useTeamHoursPerWeek(teamId: number) {
  return useQuery({
    queryKey: teamDashboardKeys.weekly(teamId),
    queryFn: () => api.get<TeamHoursPerWeek>(teamPath(teamId, 'hours/weekly')),
  })
}

export function useTeamHoursByMember(teamId: number, range: DateRange) {
  return useQuery({
    queryKey: teamDashboardKeys.byMember(teamId, range),
    queryFn: () =>
      api.get<HoursByMember>(teamPath(teamId, 'hours/by-member'), { query: rangeQuery(range) }),
    placeholderData: keepPreviousData,
  })
}

export function useTeamHoursByProject(teamId: number, range: DateRange) {
  return useQuery({
    queryKey: teamDashboardKeys.byProject(teamId, range),
    queryFn: () =>
      api.get<HoursByProject>(teamPath(teamId, 'hours/by-project'), { query: rangeQuery(range) }),
    placeholderData: keepPreviousData,
  })
}

export function useTeamHoursByCategory(teamId: number, range: DateRange) {
  return useQuery({
    queryKey: teamDashboardKeys.byCategory(teamId, range),
    queryFn: () =>
      api.get<HoursByCategory>(teamPath(teamId, 'hours/by-category'), {
        query: rangeQuery(range),
      }),
    placeholderData: keepPreviousData,
  })
}

export function useTeamTaskCounts(teamId: number, range: DateRange) {
  return useQuery({
    queryKey: teamDashboardKeys.tasks(teamId, range),
    queryFn: () => api.get<TeamTaskCounts>(teamPath(teamId, 'tasks'), { query: rangeQuery(range) }),
    placeholderData: keepPreviousData,
  })
}
