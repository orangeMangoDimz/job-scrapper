import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/core/errors/ApiError'
import { HttpClient } from '@/core/http/httpClient'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status })
}

describe('HttpClient', () => {
  it('returns envelope data on success', async () => {
    const fetchFn = vi.fn().mockResolvedValue(jsonResponse(200, { success: true, data: [1] }))
    const client = new HttpClient('/api', fetchFn)

    await expect(client.get('/runs')).resolves.toEqual([1])
    expect(fetchFn.mock.calls[0]?.[0]).toBe('/api/runs')
  })

  it('sends JSON bodies', async () => {
    const fetchFn = vi.fn().mockResolvedValue(jsonResponse(202, { success: true, data: null }))
    const client = new HttpClient('/api', fetchFn)

    await client.post('/runs', { keywords: ['a'] })

    const init = fetchFn.mock.calls[0]?.[1] as RequestInit
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"keywords":["a"]}')
  })

  it('raises ApiError with the server message', async () => {
    const fetchFn = vi
      .fn()
      .mockResolvedValue(jsonResponse(409, { success: false, error: 'Already running' }))
    const client = new HttpClient('/api', fetchFn)

    const error = await client.post('/runs', {}).catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(409)
    expect((error as ApiError).message).toBe('Already running')
  })

  it('turns network failures into ApiError', async () => {
    const fetchFn = vi.fn().mockRejectedValue(new TypeError('failed'))
    const client = new HttpClient('/api', fetchFn)

    const error = await client.get('/runs').catch((caught: unknown) => caught)

    expect((error as ApiError).status).toBe(0)
  })
})
