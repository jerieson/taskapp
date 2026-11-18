/*
 * fetch wrapper for the backend API.
 *
 * - Same-origin requests with cookies (the session cookie is httpOnly).
 * - Non-GET requests carry the double-submit CSRF token in X-CSRF-Token. If the
 *   csrf_token cookie is missing (first visit, before login) it is fetched first.
 * - A FormData body is sent as multipart (file uploads); anything else as JSON.
 * - Errors are thrown as ApiError, parsed from the standard error format.
 * - `download` saves a file response (e.g. a CSV export) under the server's file name.
 * - A 401 calls the handler registered with setUnauthorizedHandler (clears the
 *   cached user and redirects to /login), unless the request opts out.
 */
import type { components } from './schema'

export type Schemas = components['schemas']
type ErrorResponse = Schemas['ErrorResponse']

const API_BASE = '/api'
const CSRF_COOKIE = 'csrf_token'
const CSRF_HEADER = 'X-CSRF-Token'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fields: Record<string, string>

  constructor(status: number, code: string, message: string, fields?: Record<string, string>) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fields = fields ?? {}
  }
}

/** User-facing message for any thrown value. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'Something went wrong. Please try again.'
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
type QueryValue = string | number | boolean | null | undefined

export interface RequestOptions {
  query?: Record<string, QueryValue>
  body?: unknown
  /** Handle a 401 yourself instead of redirecting to /login. */
  skipAuthRedirect?: boolean
  signal?: AbortSignal
}

let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

function readCookie(name: string): string | null {
  for (const part of document.cookie.split(';')) {
    const [key, ...rest] = part.trim().split('=')
    if (key === name) return decodeURIComponent(rest.join('='))
  }
  return null
}

async function csrfToken(): Promise<string> {
  const existing = readCookie(CSRF_COOKIE)
  if (existing) return existing
  const { csrf_token } = await request<Schemas['CsrfOut']>('GET', '/auth/csrf')
  return csrf_token
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  }
  const qs = params.toString()
  return `${API_BASE}${path}${qs ? `?${qs}` : ''}`
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false
  const { error } = value
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    typeof error.code === 'string' &&
    'message' in error &&
    typeof error.message === 'string'
  )
}

async function parseError(response: Response): Promise<ApiError> {
  const body: unknown = await response.json().catch(() => null)
  if (isErrorResponse(body)) {
    const { code, message, fields } = body.error
    return new ApiError(response.status, code, message, fields ?? undefined)
  }
  // Not our format: e.g. the dev proxy answering 502 while the backend restarts.
  return new ApiError(
    response.status,
    'http_error',
    response.status >= 500
      ? 'The server is not responding. Please try again shortly.'
      : `Request failed (${response.status})`,
  )
}

async function request<T>(method: Method, path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const isForm = options.body instanceof FormData
  // FormData: the browser sets the multipart Content-Type with its boundary.
  if (options.body !== undefined && !isForm) headers['Content-Type'] = 'application/json'
  if (method !== 'GET') headers[CSRF_HEADER] = await csrfToken()

  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), {
      method,
      headers,
      credentials: 'same-origin',
      body:
        options.body === undefined
          ? undefined
          : options.body instanceof FormData
            ? options.body
            : JSON.stringify(options.body),
      signal: options.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'network_error', 'Could not reach the server. Check your connection.')
  }

  if (!response.ok) {
    const error = await parseError(response)
    if (response.status === 401 && !options.skipAuthRedirect) onUnauthorized?.()
    throw error
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** The file name from a Content-Disposition header (RFC 6266), if any. */
function attachmentName(header: string | null): string | null {
  if (!header) return null
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header)?.[1]
  if (encoded) {
    try {
      return decodeURIComponent(encoded)
    } catch {
      // Fall through to the plain parameter.
    }
  }
  return /filename="([^"]+)"/i.exec(header)?.[1] ?? null
}

/** GET a file and hand it to the browser as a download. */
async function download(
  path: string,
  query: Record<string, QueryValue>,
  fallbackName: string,
): Promise<string> {
  let response: Response
  try {
    response = await fetch(buildUrl(path, query), { credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, 'network_error', 'Could not reach the server. Check your connection.')
  }
  if (!response.ok) {
    const error = await parseError(response)
    if (response.status === 401) onUnauthorized?.()
    throw error
  }
  const name = attachmentName(response.headers.get('Content-Disposition')) ?? fallbackName
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.append(link)
  link.click()
  link.remove()
  // Give the browser a moment to start the download before releasing the blob.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  return name
}

export const api = {
  download,
  get: <T>(path: string, options?: Omit<RequestOptions, 'body'>) =>
    request<T>('GET', path, options),
  post: <T = void>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>('POST', path, { ...options, body }),
  put: <T = void>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>('PUT', path, { ...options, body }),
  patch: <T = void>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>('PATCH', path, { ...options, body }),
  delete: <T = void>(path: string, options?: RequestOptions) => request<T>('DELETE', path, options),
}
