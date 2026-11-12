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

function record(
  status: RunRecord['status'],
  discordStatus: RunRecord['discordStatus'] = null,
): RunRecord {
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
    discordStatus,
    discordSent: 0,
    discordFailed: 0,
    discordError: null,
  }
}

function detail(
  status: RunRecord['status'],
  discordStatus: RunRecord['discordStatus'] = null,
): RunDetail {
  return { record: record(status, discordStatus), jobs: [], failures: [], payloads: [] }
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

    await store.start(['django'], ['upwork'], false)
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

    await store.start(['django'], ['upwork'], false)

    expect(store.actionError).toBe('A scrape is already running.')
    expect(store.isRunning).toBe(false)
  })

  it('keeps following a run through a failed poll', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    getRun.execute
      .mockRejectedValueOnce(new Error('timeout'))
      .mockResolvedValueOnce(detail('succeeded'))
    const store = useRunStore()
    await store.start(['django'], ['upwork'], false)

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
    await store.start(['django'], ['upwork'], false)

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
    await store.start(['django'], ['upwork'], false)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * (MAX_POLL_FAILURES * 2))

    expect(store.selected?.record.status).toBe('succeeded')
  })

  it('keeps following a started run when history fails to refresh', async () => {
    startRun.execute.mockResolvedValue(record('running'))
    listRuns.execute.mockRejectedValue(new Error('timeout'))
    const store = useRunStore()

    await store.start(['django'], ['upwork'], false)

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
    await store.start(['django'], ['upwork'], false)
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
    await store.start(['django'], ['upwork'], false)

    store.stopPolling()
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

    expect(getRun.execute).not.toHaveBeenCalled()
  })

  describe('discord send', () => {
    it('passes the notify flag to the run', async () => {
      startRun.execute.mockResolvedValue(record('running'))
      const store = useRunStore()

      await store.start(['django'], ['upwork'], true)

      expect(startRun.execute).toHaveBeenCalledWith(['django'], ['upwork'], true)
    })

    it('keeps polling and stays running while the run is sending', async () => {
      startRun.execute.mockResolvedValue(record('running', 'sending'))
      getRun.execute
        .mockResolvedValueOnce(detail('succeeded', 'sending'))
        .mockResolvedValueOnce(detail('succeeded', 'sending'))
        .mockResolvedValueOnce(detail('succeeded', 'sent'))
      const store = useRunStore()
      await store.start(['django'], ['upwork'], true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isRunning).toBe(true)
      expect(store.selected?.record.status).toBe('succeeded')

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isRunning).toBe(true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isRunning).toBe(false)
      expect(store.selected?.record.discordStatus).toBe('sent')
      expect(getRun.execute).toHaveBeenCalledTimes(3)
    })

    it('refreshes the history once scraping ends and again when sending ends', async () => {
      startRun.execute.mockResolvedValue(record('running', 'sending'))
      getRun.execute
        .mockResolvedValueOnce(detail('succeeded', 'sending'))
        .mockResolvedValueOnce(detail('succeeded', 'sending'))
        .mockResolvedValueOnce(detail('succeeded', 'sent'))
      const store = useRunStore()
      await store.start(['django'], ['upwork'], true)
      listRuns.execute.mockClear()

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)

      expect(listRuns.execute).toHaveBeenCalledTimes(2)
    })

    it('follows a sending run found on load even though it is not running', async () => {
      getOptions.execute.mockResolvedValue({ keywords: [], sites: [], isStale: false })
      listRuns.execute.mockResolvedValue([record('succeeded', 'sending')])
      getRun.execute.mockResolvedValue(detail('succeeded', 'sent'))
      const store = useRunStore()

      await store.load()
      expect(store.isRunning).toBe(true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
      expect(store.isRunning).toBe(false)
    })

    it.each<[RunRecord['discordStatus']]>([['sent'], ['partial'], ['failed']])(
      'reports the outcome when sending ends as %s',
      async (final) => {
        startRun.execute.mockResolvedValue(record('running', 'sending'))
        getRun.execute
          .mockResolvedValueOnce(detail('succeeded', 'sending'))
          .mockResolvedValueOnce(detail('succeeded', final))
        const store = useRunStore()
        await store.start(['django'], ['upwork'], true)
        expect(store.discordOutcome).toBeNull()

        await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 2)

        expect(store.discordOutcome?.discordStatus).toBe(final)
      },
    )

    it('reports the outcome even when sending ends between two polls', async () => {
      startRun.execute.mockResolvedValue(record('running', 'sending'))
      getRun.execute.mockResolvedValueOnce(detail('succeeded', 'sent'))
      const store = useRunStore()
      await store.start(['django'], ['upwork'], true)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(store.discordOutcome?.discordStatus).toBe('sent')
    })

    it('does not report an outcome for a run without a send', async () => {
      startRun.execute.mockResolvedValue(record('running'))
      getRun.execute.mockResolvedValueOnce(detail('succeeded'))
      const store = useRunStore()
      await store.start(['django'], ['upwork'], false)

      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

      expect(store.discordOutcome).toBeNull()
    })

    it('does not report an outcome for a run that was only selected', async () => {
      getRun.execute.mockResolvedValue(detail('succeeded', 'sent'))
      const store = useRunStore()

      await store.select('run-1')

      expect(store.discordOutcome).toBeNull()
    })
  })
})
