import { useParams } from 'react-router'

import { ApiError } from '../api/client'

/** The `:id` route param as a positive integer, or null when it is not one. */
export function useIdParam(): number | null {
  const { id } = useParams()
  return id && /^\d+$/.test(id) ? Number(id) : null
}

/** True for an API 404 (a missing record, or one the user may not see). */
export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}
