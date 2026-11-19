/*
 * AI-assisted features. Every call sends user text to the configured AI provider and
 * counts toward the daily AI limit (429 `ai_daily_limit_exceeded`). Results are drafts:
 * nothing is saved until the user confirms through the normal endpoints.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type Schemas } from './client'

export type LogDraft = Schemas['LogDraftOut']
export type TeamSummary = Schemas['TeamSummaryOut']
export type TeamSummaryResult = Schemas['TeamSummaryResult']
export type TeamSummaryPage = Schemas['Page_TeamSummaryOut_']
export type LogDraftRow = Schemas['LogDraftRow']
export type LogDraftField = LogDraftRow['missing_fields'][number]

/** Must match LOG_DRAFT_MAX_CHARS in app/schemas/ai.py. */
export const LOG_DRAFT_MAX_CHARS = 2000

export function useLogDraft() {
  return useMutation({
    mutationFn: (text: string) => api.post<LogDraft>('/ai/log-draft', { text }),
  })
}

// ---------------------------------------------------------------- team summary
// Managers: their own team; admins: any team. A summary for the same team and period
// is returned from the database (no AI call) unless `regenerate` is set.

export const aiKeys = {
  all: ['ai'] as const,
  teamSummaries: (teamId: number) => ['ai', 'team-summaries', teamId] as const,
  teamSummaryPage: (teamId: number, offset: number) =>
    ['ai', 'team-summaries', teamId, offset] as const,
}

export const TEAM_SUMMARY_PAGE_SIZE = 10

export function useTeamSummaries(teamId: number, offset = 0) {
  return useQuery({
    queryKey: aiKeys.teamSummaryPage(teamId, offset),
    queryFn: () =>
      api.get<TeamSummaryPage>('/ai/team-summaries', {
        query: { team_id: teamId, limit: TEAM_SUMMARY_PAGE_SIZE, offset },
      }),
    placeholderData: keepPreviousData,
  })
}

export interface TeamSummaryRequest {
  teamId: number
  from: string
  to: string
  regenerate: boolean
}

export function useTeamSummary() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ teamId, from, to, regenerate }: TeamSummaryRequest) =>
      api.post<TeamSummaryResult>('/ai/team-summary', {
        team_id: teamId,
        period_start: from,
        period_end: to,
        regenerate,
      }),
    onSuccess: (result) => {
      if (!result.cached) {
        void queryClient.invalidateQueries({ queryKey: aiKeys.teamSummaries(result.team_id) })
      }
    },
  })
}
