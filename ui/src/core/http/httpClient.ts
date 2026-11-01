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

  get<T>(path: string): Promise<T> {
    return this.request<T>('GET', path)
  }

  post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>('POST', path, body)
  }

  put<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>('PUT', path, body)
  }

  private async request<T>(method: HttpMethod, path: string, body?: unknown): Promise<T> {
    const response = await this.send(method, path, body)
    if (!response.ok) {
      throw await toApiError(response)
    }
    return unwrapEnvelope<T>(response)
  }

  private async send(method: HttpMethod, path: string, body?: unknown): Promise<Response> {
    try {
      return await this.fetchFn(`${this.baseUrl}${path}`, {
        method,
        credentials: 'same-origin',
        headers: body === undefined ? {} : { 'Content-Type': JSON_CONTENT_TYPE },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
      })
    } catch (error) {
      throw toNetworkError(error)
    }
  }
}

export const httpClient = new HttpClient(env.apiBaseUrl)
