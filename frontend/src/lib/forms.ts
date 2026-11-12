import type { FieldValues, Path, UseFormSetError } from 'react-hook-form'
import { z } from 'zod'

import { ApiError } from '../api/client'

// Mirrors the backend rules in app/schemas/auth.py.
export const PASSWORD_MIN_LENGTH = 8
export const PASSWORD_MAX_LENGTH = 128

export const newPasswordSchema = z
  .string()
  .min(PASSWORD_MIN_LENGTH, `Use at least ${PASSWORD_MIN_LENGTH} characters`)
  .max(PASSWORD_MAX_LENGTH, `Use at most ${PASSWORD_MAX_LENGTH} characters`)

export const usernameSchema = z
  .string()
  .trim()
  .regex(/^[A-Za-z0-9._-]{3,50}$/, '3-50 characters: letters, digits, dot, underscore or hyphen')

export const confirmPasswordSchema = z.string().min(1, 'Repeat the password')
export const PASSWORDS_DIFFER = 'Passwords do not match'

/**
 * Copy field errors from an API error onto the form. Returns true if any field
 * matched, so the caller can skip a form-level message.
 */
export function applyFieldErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  knownFields: readonly Path<T>[],
): boolean {
  if (!(error instanceof ApiError)) return false
  let matched = false
  for (const [field, message] of Object.entries(error.fields)) {
    const name = knownFields.find((known) => known === field)
    if (name) {
      setError(name, { type: 'server', message })
      matched = true
    }
  }
  return matched
}

/** Only follow same-app paths after login (never `//evil.com` or full URLs). */
export function safeNextPath(next: string | null): string | null {
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) return null
  return next
}
