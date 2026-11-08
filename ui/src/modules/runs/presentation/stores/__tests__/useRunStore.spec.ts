import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { RunDetail, RunRecord } from '@/modules/runs/domain/entities/Run'
import { provideRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'
import {
  MAX_POLL_FAILURES,
  POLL_INTERVAL_MS,
  useRunStore,
} from '@/modules/runs/presentation/stores/useRunStore'

const getOptions = { execute: vi.fn() }
const getRun = { execute: vi.fn() }
const listRuns = { execute: vi.fn() }
const startRun = { execute: vi.fn() }

function record(status: RunRecord['status']): RunRecord {
  return {
    id: 'run-1',
    status,
    keywords: ['django'],
    sites: ['upwork'],
    startedAt: '2026-11-01T10:00:00+00:00',
    finishedAt: null,
    jobCount: 0,
    errorCount: 0,
    error: null,
  }
}

function detail(status: RunRecord['status']): RunDetail {
  return { record: record(status), jobs: [], failures: [], payloads: [] }
}

describe('useRunStore', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.useFakeTimers()
    setActivePinia(createPinia())
    provideRunUseCases({ getOptions, getRun, listRuns, startRun })
    listRuns.execute.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads options and history', async () => {
    getOptions.execute.mockResolvedValue({
      keywords: ['django'],
      sites: [{ name: 'upwork', isEnabled: true }],
      isStale: false,
    })
    const store = useRunStore()

    await store.load()

    expect(store.status).toBe('ready')
    expect(store.options?.keywords).toEqual(['django'])
  })

  it('shows an error when options fail', async () => {
    getOptions.execute.mockRejectedValue(new Error('Scraper down'))
    const store = useRunStore()

    await store.load()

    expect(store.status).toBe('error')
    expect(store.errorMessage).toBe('Scraper down')
  })

  it('polls a started run until it ends', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    getRun.execute
      .mockResolvedValueOnce(detail('running'))
      .mockResolvedValueOnce(detail('succeeded'))
    const store = useRunStore()

    await store.start(['django'], ['upwork'])
    expect(store.isRunning).toBe(true)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.isRunning).toBe(true)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.isRunning).toBe(false)
    expect(store.selected?.record.status).toBe('succeeded')
    expect(getRun.execute).toHaveBeenCalledTimes(2)
  })

  it('keeps the message when a run cannot start', async () => {
    startRun.execute.mockRejectedValue(new Error('A scrape is already running.'))
    const store = useRunStore()

    await store.start(['django'], ['upwork'])

    expect(store.actionError).toBe('A scrape is already running.')
    expect(store.isRunning).toBe(false)
  })

  it('keeps following a run through a failed poll', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    getRun.execute
      .mockRejectedValueOnce(new Error('timeout'))
      .mockResolvedValueOnce(detail('succeeded'))
    const store = useRunStore()
    await store.start(['django'], ['upwork'])

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.isRunning).toBe(true)
    expect(store.actionError).toBeNull()

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    expect(store.isRunning).toBe(false)
    expect(store.selected?.record.status).toBe('succeeded')
  })

  it('gives up after repeated failed polls', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    getRun.execute.mockRejectedValue(new Error('timeout'))
    const store = useRunStore()
    await store.start(['django'], ['upwork'])

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * MAX_POLL_FAILURES)

    expect(store.isRunning).toBe(false)
    expect(store.actionError).toContain('Lost track')
    expect(getRun.execute).toHaveBeenCalledTimes(MAX_POLL_FAILURES)
  })

  it('counts only failures in a row', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    const failures = Array.from({ length: MAX_POLL_FAILURES - 1 }, () => new Error('timeout'))
    for (const failure of [...failures, null, ...failures]) {
      if (failure === null) {
        getRun.execute.mockResolvedValueOnce(detail('running'))
      } else {
        getRun.execute.mockRejectedValueOnce(failure)
      }
    }
    getRun.execute.mockResolvedValueOnce(detail('succeeded'))
    const store = useRunStore()
    await store.start(['django'], ['upwork'])

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * (MAX_POLL_FAILURES * 2))

    expect(store.selected?.record.status).toBe('succeeded')
  })

  it('keeps following a started run when history fails to refresh', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    listRuns.execute.mockRejectedValue(new Error('timeout'))
    const store = useRunStore()

    await store.start(['django'], ['upwork'])

    expect(store.isRunning).toBe(true)
    expect(store.actionError).toContain('history')
  })

  it('ignores a poll that returns after polling stopped', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    let finishPoll: (value: RunDetail) => void = () => undefined
    getRun.execute.mockReturnValueOnce(
      new Promise<RunDetail>((resolve) => {
        finishPoll = resolve
      }),
    )
    const store = useRunStore()
    await store.start(['django'], ['upwork'])
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

    store.stopPolling()
    finishPoll(detail('running'))
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

    expect(getRun.execute).toHaveBeenCalledTimes(1)
    expect(store.isRunning).toBe(false)
  })

  it('stops polling when asked', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    getRun.execute.mockResolvedValue(detail('running'))
    const store = useRunStore()
    await store.start(['django'], ['upwork'])

    store.stopPolling()
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

    expect(getRun.execute).not.toHaveBeenCalled()
  })
})
