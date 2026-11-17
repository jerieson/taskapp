/*
 * AI-assisted features. Every call sends user text to the configured AI provider and
 * counts toward the daily AI limit (429 `ai_daily_limit_exceeded`). Results are drafts:
 * nothing is saved until the user confirms through the normal endpoints.
 */
import { useMutation } from '@tanstack/react-query'

import { api, type Schemas } from './client'

export type LogDraft = Schemas['LogDraftOut']
export type LogDraftField = LogDraft['missing_fields'][number]

/** Must match LOG_DRAFT_MAX_CHARS in app/schemas/ai.py. */
export const LOG_DRAFT_MAX_CHARS = 2000

export function useLogDraft() {
  return useMutation({
    mutationFn: (text: string) => api.post<LogDraft>('/ai/log-draft', { text }),
  })
}
