import { ApiError } from '@/core/errors/ApiError'

type FieldErrors = Record<string, string[]>

const DEFAULT_MESSAGE = 'Something went wrong. Try again.'
const UNREACHABLE_MESSAGE = 'Could not reach the server.'
const TIMEOUT_MESSAGE = 'The server took too long to respond.'
const TIMEOUT_ERROR_NAMES = ['TimeoutError', 'AbortError']

const STATUS_MESSAGES: Record<number, string> = {
  401: 'You are not signed in.',
  404: 'Not found.',
  413: 'That file is too large.',
  429: 'Too many requests. Try again in a moment.',
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isTimeoutError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'name' in error &&
    TIMEOUT_ERROR_NAMES.includes(String(error.name))
  )
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return undefined
  }
}

function toMessages(value: unknown): string[] {
  if (typeof value === 'string') {
    return value.trim() === '' ? [] : [value]
  }
  if (Array.isArray(value)) {
    return value.flatMap(toMessages)
  }
  if (isRecord(value)) {
    return Object.values(value).flatMap(toMessages)
  }
  return []
}

function toEntries(field: string, value: unknown): [string, unknown][] {
  if (!isRecord(value)) {
    return [[field, value]]
  }
  return Object.entries(value).map(([key, nested]) => [`${field}.${key}`, nested])
}

function flattenFieldErrors(error: Record<string, unknown>): FieldErrors {
  const fieldErrors: FieldErrors = {}
  for (const [field, value] of Object.entries(error)) {
    for (const [key, nested] of toEntries(field, value)) {
      const messages = toMessages(nested)
      if (messages.length > 0) {
        fieldErrors[key] = messages
      }
    }
  }
  return fieldErrors
}

export async function toApiError(response: Response): Promise<ApiError> {
  const body = await readJson(response)
  const error = isRecord(body) ? body.error : undefined
  const data = isRecord(body) ? (body.data ?? null) : null
  const fallback = STATUS_MESSAGES[response.status] ?? DEFAULT_MESSAGE

  if (typeof error === 'string' && error.trim() !== '') {
    return new ApiError(response.status, error, {}, data)
  }

  if (isRecord(error)) {
    const fieldErrors = flattenFieldErrors(error)
    const message = Object.values(fieldErrors).flat().join(' ')
    return new ApiError(response.status, message || fallback, fieldErrors, data)
  }

  return new ApiError(response.status, fallback, {}, data)
}

export function toNetworkError(error: unknown): ApiError {
  return new ApiError(0, isTimeoutError(error) ? TIMEOUT_MESSAGE : UNREACHABLE_MESSAGE)
}
