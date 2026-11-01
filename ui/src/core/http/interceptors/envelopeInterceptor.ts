import { ApiError } from '@/core/errors/ApiError'

const UNEXPECTED_MESSAGE = 'The server sent an unexpected response.'
const NO_CONTENT_STATUS = 204

interface SuccessEnvelope {
  success: true
  data: unknown
  meta?: unknown
}

export interface EnvelopeWithMeta<T, M> {
  data: T
  meta: M
}

function isSuccessEnvelope(value: unknown): value is SuccessEnvelope {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    'success' in value &&
    value.success === true
  )
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return undefined
  }
}

async function readSuccessEnvelope(response: Response): Promise<SuccessEnvelope> {
  const body = await readJson(response)
  if (!isSuccessEnvelope(body)) {
    throw new ApiError(response.status, UNEXPECTED_MESSAGE)
  }
  return body
}

export async function unwrapEnvelope<T>(response: Response): Promise<T> {
  if (response.status === NO_CONTENT_STATUS) {
    return undefined as T
  }

  return (await readSuccessEnvelope(response)).data as T
}

export async function unwrapEnvelopeWithMeta<T, M>(
  response: Response,
): Promise<EnvelopeWithMeta<T, M>> {
  const body = await readSuccessEnvelope(response)
  return { data: body.data as T, meta: body.meta as M }
}
