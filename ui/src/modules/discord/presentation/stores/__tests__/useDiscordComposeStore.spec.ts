import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { DiscordChannel, DiscordSettings } from '@/modules/discord/domain/entities/Discord'
import { provideDiscordUseCases } from '@/modules/discord/presentation/stores/discordUseCases'
import { useDiscordComposeStore } from '@/modules/discord/presentation/stores/useDiscordComposeStore'
import type { RunDetail, RunRecord } from '@/modules/runs/domain/entities/Run'
import { provideRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'

const getSettings = { execute: vi.fn() }
const saveSettings = { execute: vi.fn() }
const testConnection = { execute: vi.fn() }
const listChannels = { execute: vi.fn() }
const previewMessage = { execute: vi.fn() }
const sendMessage = { execute: vi.fn() }
const getOptions = { execute: vi.fn() }
const getRun = { execute: vi.fn() }
const listRuns = { execute: vi.fn() }
const startRun = { execute: vi.fn() }

const CHANNEL_ID = '12345678901234567'
const USER_ID = '76543210987654321'

const CHANNELS: DiscordChannel[] = [
  { id: CHANNEL_ID, name: 'jobs', guildId: '1', guildName: 'Home' },
  { id: '22345678901234567', name: 'general', guildId: '1', guildName: 'Home' },
]

const SETTINGS: DiscordSettings = {
  isConfigured: true,
  tokenHint: '••••1234',
  defaultChannelId: CHANNEL_ID,
  mentionUserId: USER_ID,
  messageTemplate: '{title}',
  maxChars: 1900,
  updatedAt: null,
}

function makeRun(id: string, jobCount: number): RunRecord {
  return {
    id,
    status: 'succeeded',
    keywords: ['django'],
    sites: ['upwork'],
    startedAt: '2026-11-01T10:00:00+00:00',
    finishedAt: null,
    jobCount,
    errorCount: 0,
    error: null,
  }
}

function makeDetail(id: string, jobCount: number): RunDetail {
  return {
    record: makeRun(id, jobCount),
    jobs: Array.from({ length: jobCount }, (_, index) => ({
      site: 'upwork',
      matchedKeyword: 'django',
      title: `Job ${index}`,
      company: 'Acme',
      location: null,
      url: null,
      postedAt: null,
    })),
    failures: [],
    payloads: [],
  }
}

function deferred<T>(): {
  promise: Promise<T>
  resolve: (value: T) => void
  reject: (reason: unknown) => void
} {
  let resolve: (value: T) => void = () => undefined
  let reject: (reason: unknown) => void = () => undefined
  const promise = new Promise<T>((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}

async function loadedStore(settings: DiscordSettings = SETTINGS) {
  const store = useDiscordComposeStore()
  await store.load(settings)
  return store
}

describe('useDiscordComposeStore', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    provideDiscordUseCases({
      getSettings,
      saveSettings,
      testConnection,
      listChannels,
      previewMessage,
      sendMessage,
    })
    provideRunUseCases({ getOptions, getRun, listRuns, startRun })
    listChannels.execute.mockResolvedValue(CHANNELS)
    listRuns.execute.mockResolvedValue([makeRun('r1', 3), makeRun('r2', 0), makeRun('r3', 60)])
    getRun.execute.mockImplementation((id: string) =>
      Promise.resolve(makeDetail(id, id === 'r3' ? 60 : 3)),
    )
  })

  describe('load', () => {
    it('loads the channels and the runs', async () => {
      const store = await loadedStore()

      expect(store.status).toBe('ready')
      expect(store.channels).toEqual(CHANNELS)
      expect(store.runs).toHaveLength(3)
    })

    it('picks the default channel', async () => {
      const store = await loadedStore()

      expect(store.channelId).toBe(CHANNEL_ID)
    })

    it('leaves the channel empty when the default is not in the list', async () => {
      const store = await loadedStore({ ...SETTINGS, defaultChannelId: '99999999999999999' })

      expect(store.channelId).toBeNull()
    })

    it('leaves the channel empty when there is no default', async () => {
      const store = await loadedStore({ ...SETTINGS, defaultChannelId: null })

      expect(store.channelId).toBeNull()
    })

    it('turns mention on when a user id is saved', async () => {
      const store = await loadedStore()

      expect(store.hasMentionUser).toBe(true)
      expect(store.mention).toBe(true)
    })

    it('has no mention user without a saved user id', async () => {
      const store = await loadedStore({ ...SETTINGS, mentionUserId: null })

      expect(store.hasMentionUser).toBe(false)
    })

    it('shows an error when the channels fail', async () => {
      listChannels.execute.mockRejectedValue(new Error('Discord rejected the bot token.'))
      const store = await loadedStore()

      expect(store.status).toBe('error')
      expect(store.errorMessage).toBe('Discord rejected the bot token.')
    })

    it('shows an error when the runs fail', async () => {
      listRuns.execute.mockRejectedValue(new Error('Runs down'))
      const store = await loadedStore()

      expect(store.status).toBe('error')
      expect(store.errorMessage).toBe('Runs down')
    })

    it('offers only the runs that found jobs', async () => {
      const store = await loadedStore()

      expect(store.sendableRuns.map((run) => run.id)).toEqual(['r1', 'r3'])
    })
  })

  describe('free text', () => {
    it('counts the mention prefix in the char count', async () => {
      const store = await loadedStore()
      store.text = 'hello'

      expect(store.charCount).toBe(`<@${USER_ID}>\n`.length + 5)
    })

    it('drops the prefix from the count when mention is off', async () => {
      const store = await loadedStore()
      store.text = 'hello'
      store.mention = false

      expect(store.charCount).toBe(5)
    })

    it('is over the limit past 2000 chars with the prefix', async () => {
      const store = await loadedStore()
      store.text = 'a'.repeat(2000)

      expect(store.isOverLimit).toBe(true)
      expect(store.canSend).toBe(false)
      expect(store.canPreview).toBe(false)
    })

    it('is at the limit when the text and prefix make exactly 2000', async () => {
      const store = await loadedStore()
      store.text = 'a'.repeat(2000 - `<@${USER_ID}>\n`.length)

      expect(store.isOverLimit).toBe(false)
      expect(store.canSend).toBe(true)
    })

    it('cannot send an empty text', async () => {
      const store = await loadedStore()
      store.text = '   '

      expect(store.canSend).toBe(false)
      expect(store.canPreview).toBe(false)
    })

    it('cannot send without a channel', async () => {
      const store = await loadedStore({ ...SETTINGS, defaultChannelId: null })
      store.text = 'hello'

      expect(store.canSend).toBe(false)
      expect(store.canPreview).toBe(true)
    })

    it('previews with the mention flag and the text', async () => {
      previewMessage.execute.mockResolvedValue(['<@1>\nhello'])
      const store = await loadedStore()
      store.text = 'hello'

      await store.preview()

      expect(previewMessage.execute).toHaveBeenCalledWith(true, { kind: 'text', text: 'hello' })
      expect(store.previewMessages).toEqual(['<@1>\nhello'])
      expect(store.isPreviewing).toBe(false)
    })

    it('keeps the message when the preview fails', async () => {
      previewMessage.execute.mockRejectedValue(new Error('Text is too long'))
      const store = await loadedStore()
      store.text = 'hello'

      await store.preview()

      expect(store.previewError).toBe('Text is too long')
      expect(store.previewMessages).toEqual([])
    })

    it('clears the preview when the text changes', async () => {
      previewMessage.execute.mockResolvedValue(['hello'])
      const store = await loadedStore()
      store.text = 'hello'
      await store.preview()

      store.text = 'hello again'
      await Promise.resolve()

      expect(store.previewMessages).toEqual([])
    })

    it('clears the preview when mention changes', async () => {
      previewMessage.execute.mockResolvedValue(['hello'])
      const store = await loadedStore()
      store.text = 'hello'
      await store.preview()

      store.mention = false
      await Promise.resolve()

      expect(store.previewMessages).toEqual([])
    })

    it('sends to the channel with mention on', async () => {
      const result = { sent: 1, failed: 0, results: [] }
      sendMessage.execute.mockResolvedValue(result)
      const store = await loadedStore()
      store.text = 'hello'

      await expect(store.send()).resolves.toEqual(result)

      expect(sendMessage.execute).toHaveBeenCalledWith(CHANNEL_ID, true, {
        kind: 'text',
        text: 'hello',
      })
      expect(store.sendResult).toEqual(result)
      expect(store.isSending).toBe(false)
    })

    it('sends mention off when no user id is saved', async () => {
      sendMessage.execute.mockResolvedValue({ sent: 1, failed: 0, results: [] })
      const store = await loadedStore({ ...SETTINGS, mentionUserId: null })
      store.text = 'hello'

      await store.send()

      expect(sendMessage.execute).toHaveBeenCalledWith(CHANNEL_ID, false, {
        kind: 'text',
        text: 'hello',
      })
    })

    it('sends mention off when the box is unticked', async () => {
      sendMessage.execute.mockResolvedValue({ sent: 1, failed: 0, results: [] })
      const store = await loadedStore()
      store.text = 'hello'
      store.mention = false

      await store.send()

      expect(sendMessage.execute).toHaveBeenCalledWith(CHANNEL_ID, false, {
        kind: 'text',
        text: 'hello',
      })
    })

    it('keeps the message and returns null when send fails', async () => {
      sendMessage.execute.mockRejectedValue(new Error("The bot can't post in that channel."))
      const store = await loadedStore()
      store.text = 'hello'

      await expect(store.send()).resolves.toBeNull()

      expect(store.sendError).toBe("The bot can't post in that channel.")
      expect(store.isSending).toBe(false)
    })

    it('does not send when it cannot send', async () => {
      const store = await loadedStore()

      await expect(store.send()).resolves.toBeNull()

      expect(sendMessage.execute).not.toHaveBeenCalled()
    })

    it('cannot send while a preview is in flight', async () => {
      const pending = deferred<string[]>()
      previewMessage.execute.mockReturnValue(pending.promise)
      const store = await loadedStore()
      store.text = 'hello'

      const previewing = store.preview()

      expect(store.isPreviewing).toBe(true)
      expect(store.canSend).toBe(false)

      pending.resolve(['hello'])
      await previewing

      expect(store.canSend).toBe(true)
    })

    it('cannot send again while a send is in progress', async () => {
      const pending = deferred<{ sent: number; failed: number; results: [] }>()
      sendMessage.execute.mockReturnValue(pending.promise)
      const store = await loadedStore()
      store.text = 'hello'

      const first = store.send()
      const second = store.send()

      expect(store.canSend).toBe(false)
      await expect(second).resolves.toBeNull()
      expect(sendMessage.execute).toHaveBeenCalledTimes(1)

      pending.resolve({ sent: 1, failed: 0, results: [] })
      await first
    })

    it('drops a preview that answers after the text changed', async () => {
      const pending = deferred<string[]>()
      previewMessage.execute.mockReturnValue(pending.promise)
      const store = await loadedStore()
      store.text = 'hello'

      const previewing = store.preview()
      store.text = 'hello again'
      await Promise.resolve()
      pending.resolve(['hello'])
      await previewing

      expect(store.previewMessages).toEqual([])
      expect(store.isPreviewing).toBe(false)
    })

    it('drops a failed preview that answers after the text changed', async () => {
      const pending = deferred<string[]>()
      previewMessage.execute.mockReturnValue(pending.promise)
      const store = await loadedStore()
      store.text = 'hello'

      const previewing = store.preview()
      store.text = 'hello again'
      await Promise.resolve()
      pending.reject(new Error('Text is too long'))
      await previewing

      expect(store.previewError).toBeNull()
    })

    it('keeps the newest preview when an older one answers last', async () => {
      const slow = deferred<string[]>()
      const fast = deferred<string[]>()
      previewMessage.execute.mockReturnValueOnce(slow.promise).mockReturnValueOnce(fast.promise)
      const store = await loadedStore()
      store.text = 'hello'

      const first = store.preview()
      store.text = 'hello again'
      await Promise.resolve()
      const second = store.preview()
      fast.resolve(['hello again'])
      await second
      slow.resolve(['hello'])
      await first

      expect(store.previewMessages).toEqual(['hello again'])
      expect(store.isPreviewing).toBe(false)
    })

    it('clears an earlier result when a new send starts', async () => {
      sendMessage.execute
        .mockResolvedValueOnce({ sent: 1, failed: 0, results: [] })
        .mockRejectedValueOnce(new Error('Nope'))
      const store = await loadedStore()
      store.text = 'hello'
      await store.send()

      await store.send()

      expect(store.sendResult).toBeNull()
      expect(store.sendError).toBe('Nope')
    })
  })

  describe('scraper result', () => {
    it('loads the run and ticks every job', async () => {
      const store = await loadedStore()
      store.mode = 'jobs'

      await store.selectRun('r1')

      expect(getRun.execute).toHaveBeenCalledWith('r1')
      expect(store.detail?.record.id).toBe('r1')
      expect(store.pickedIndexes).toEqual([0, 1, 2])
    })

    it('shows an error when the run fails to load', async () => {
      getRun.execute.mockRejectedValue(new Error('Run gone'))
      const store = await loadedStore()

      await store.selectRun('r1')

      expect(store.runError).toBe('Run gone')
      expect(store.detail).toBeNull()
      expect(store.isLoadingRun).toBe(false)
    })

    it('unticks and reticks a job', async () => {
      const store = await loadedStore()
      await store.selectRun('r1')

      store.setJobPicked(1, false)
      expect(store.pickedIndexes).toEqual([0, 2])

      store.setJobPicked(1, true)
      expect(store.pickedIndexes).toEqual([0, 1, 2])
    })

    it('does not tick a job twice', async () => {
      const store = await loadedStore()
      await store.selectRun('r1')

      store.setJobPicked(1, true)

      expect(store.pickedIndexes).toEqual([0, 1, 2])
    })

    it('clears and reselects every job', async () => {
      const store = await loadedStore()
      await store.selectRun('r1')

      store.clearJobs()
      expect(store.pickedIndexes).toEqual([])

      store.pickAllJobs()
      expect(store.pickedIndexes).toEqual([0, 1, 2])
    })

    it('cannot send with no job ticked', async () => {
      const store = await loadedStore()
      store.mode = 'jobs'
      await store.selectRun('r1')

      store.clearJobs()

      expect(store.canSend).toBe(false)
      expect(store.canPreview).toBe(false)
    })

    it('cannot send before a run is picked', async () => {
      const store = await loadedStore()
      store.mode = 'jobs'

      expect(store.canSend).toBe(false)
    })

    it('ticks only the first 50 jobs of a bigger run', async () => {
      const store = await loadedStore()
      store.mode = 'jobs'
      await store.selectRun('r3')

      expect(store.pickedIndexes).toEqual(Array.from({ length: 50 }, (_, index) => index))
      expect(store.isOverLimit).toBe(false)
      expect(store.canSend).toBe(true)
    })

    it('is over the limit when more than 50 jobs get ticked', async () => {
      const store = await loadedStore()
      store.mode = 'jobs'
      await store.selectRun('r3')

      store.setJobPicked(50, true)

      expect(store.pickedIndexes).toHaveLength(51)
      expect(store.isOverLimit).toBe(true)
      expect(store.canSend).toBe(false)
    })

    it('ticks every job of a bigger run with pick all and clears with clear all', async () => {
      const store = await loadedStore()
      store.mode = 'jobs'
      await store.selectRun('r3')

      store.pickAllJobs()
      expect(store.pickedIndexes).toHaveLength(60)
      expect(store.isOverLimit).toBe(true)

      store.clearJobs()
      expect(store.pickedIndexes).toEqual([])
    })

    it('keeps the latest run when an older run answers last', async () => {
      const slow = deferred<RunDetail>()
      const fast = deferred<RunDetail>()
      getRun.execute.mockReturnValueOnce(slow.promise).mockReturnValueOnce(fast.promise)
      const store = await loadedStore()

      const first = store.selectRun('r1')
      const second = store.selectRun('r3')
      fast.resolve(makeDetail('r3', 60))
      await second
      slow.resolve(makeDetail('r1', 3))
      await first

      expect(store.detail?.record.id).toBe('r3')
      expect(store.pickedIndexes).toHaveLength(50)
      expect(store.isLoadingRun).toBe(false)
    })

    it('keeps the latest run when an older run answers first', async () => {
      const slow = deferred<RunDetail>()
      const fast = deferred<RunDetail>()
      getRun.execute.mockReturnValueOnce(slow.promise).mockReturnValueOnce(fast.promise)
      const store = await loadedStore()

      const first = store.selectRun('r1')
      const second = store.selectRun('r3')
      slow.resolve(makeDetail('r1', 3))
      await first

      expect(store.detail).toBeNull()
      expect(store.isLoadingRun).toBe(true)

      fast.resolve(makeDetail('r3', 60))
      await second

      expect(store.detail?.record.id).toBe('r3')
      expect(store.isLoadingRun).toBe(false)
    })

    it('ignores the error of an older run', async () => {
      const slow = deferred<RunDetail>()
      const fast = deferred<RunDetail>()
      getRun.execute.mockReturnValueOnce(slow.promise).mockReturnValueOnce(fast.promise)
      const store = await loadedStore()

      const first = store.selectRun('r1')
      const second = store.selectRun('r3')
      fast.resolve(makeDetail('r3', 60))
      await second
      slow.reject(new Error('Run gone'))
      await first

      expect(store.runError).toBeNull()
      expect(store.detail?.record.id).toBe('r3')
    })

    it('cannot send while a run is loading', async () => {
      const store = await loadedStore()
      store.mode = 'jobs'
      await store.selectRun('r1')
      const next = deferred<RunDetail>()
      getRun.execute.mockReturnValueOnce(next.promise)

      const loading = store.selectRun('r3')

      expect(store.isLoadingRun).toBe(true)
      expect(store.canSend).toBe(false)

      next.resolve(makeDetail('r3', 60))
      await loading

      expect(store.canSend).toBe(true)
    })

    it('previews and sends the run id and the ticked indexes in order', async () => {
      previewMessage.execute.mockResolvedValue(['a', 'b'])
      sendMessage.execute.mockResolvedValue({ sent: 3, failed: 0, results: [] })
      const store = await loadedStore()
      store.mode = 'jobs'
      await store.selectRun('r1')
      store.setJobPicked(1, false)
      store.setJobPicked(1, true)

      await store.preview()
      await store.send()

      const content = { kind: 'jobs', runId: 'r1', jobIndexes: [0, 1, 2] }
      expect(previewMessage.execute).toHaveBeenCalledWith(true, content)
      expect(sendMessage.execute).toHaveBeenCalledWith(CHANNEL_ID, true, content)
    })

    it('ignores free text while in scraper mode', async () => {
      const store = await loadedStore()
      store.text = 'hello'
      store.mode = 'jobs'

      expect(store.canSend).toBe(false)
    })

    it('clears the preview when a job is unticked', async () => {
      previewMessage.execute.mockResolvedValue(['a'])
      const store = await loadedStore()
      store.mode = 'jobs'
      await store.selectRun('r1')
      await store.preview()

      store.setJobPicked(0, false)
      await Promise.resolve()

      expect(store.previewMessages).toEqual([])
    })

    it('does not count characters for jobs', async () => {
      const store = await loadedStore()
      store.mode = 'jobs'

      expect(store.isOverLimit).toBe(false)
    })
  })
})
