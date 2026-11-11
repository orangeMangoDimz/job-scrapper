import { env } from '@/core/config/env'
import { unwrapEnvelope } from '@/core/http/interceptors/envelopeInterceptor'
import { toApiError, toNetworkError } from '@/core/http/interceptors/errorInterceptor'

const DEFAULT_TIMEOUT_MS = 15_000
const JSON_CONTENT_TYPE = 'application/json'

type HttpMethod = 'GET' | 'POST' | 'PUT'

export class HttpClient {
  private readonly baseUrl: string
  private readonly fetchFn: typeof fetch

  constructor(baseUrl: string, fetchFn: typeof fetch = (...args) => fetch(...args)) {
    this.baseUrl = baseUrl
    this.fetchFn = fetchFn
  }

  get<T>(path: string, timeoutMs?: number): Promise<T> {
    return this.request<T>('GET', path, undefined, timeoutMs)
  }

  post<T>(path: string, body?: unknown, timeoutMs?: number): Promise<T> {
    return this.request<T>('POST', path, body, timeoutMs)
  }

  put<T>(path: string, body: unknown, timeoutMs?: number): Promise<T> {
    return this.request<T>('PUT', path, body, timeoutMs)
  }

  private async request<T>(
    method: HttpMethod,
    path: string,
    body?: unknown,
    timeoutMs?: number,
  ): Promise<T> {
    const response = await this.send(method, path, body, timeoutMs)
    if (!response.ok) {
      throw await toApiError(response)
    }
    return unwrapEnvelope<T>(response)
  }

  private async send(
    method: HttpMethod,
    path: string,
    body?: unknown,
    timeoutMs: number = DEFAULT_TIMEOUT_MS,
  ): Promise<Response> {
    try {
      return await this.fetchFn(`${this.baseUrl}${path}`, {
        method,
        credentials: 'same-origin',
        headers: body === undefined ? {} : { 'Content-Type': JSON_CONTENT_TYPE },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(timeoutMs),
      })
    } catch (error) {
      throw toNetworkError(error)
    }
  }
}

export const httpClient = new HttpClient(env.apiBaseUrl)
