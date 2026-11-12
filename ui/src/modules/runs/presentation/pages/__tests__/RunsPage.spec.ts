import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { nextTick } from 'vue'

import { createMemoryStorage } from '@/__tests__/memoryStorage'
import { EMPTY_FILTER, type ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import type { DiscordSettings } from '@/modules/discord/domain/entities/Discord'
import { provideDiscordUseCases } from '@/modules/discord/presentation/stores/discordUseCases'
import type { RunDetail, RunOptions, RunRecord } from '@/modules/runs/domain/entities/Run'
import RunsPage from '@/modules/runs/presentation/pages/RunsPage.vue'
import { provideRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'
import { POLL_INTERVAL_MS, useRunStore } from '@/modules/runs/presentation/stores/useRunStore'

const toast = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }))
vi.mock('vue-sonner', () => ({ toast }))

const getSettings = { execute: vi.fn() }
const getOptions = { execute: vi.fn() }
const getRun = { execute: vi.fn() }
const listRuns = { execute: vi.fn() }
const startRun = { execute: vi.fn() }

const OPTIONS: RunOptions = {
  keywords: ['django'],
  sites: [{ name: 'upwork', isEnabled: true }],
  isStale: false,
}

const RUN: RunRecord = {
  id: 'run-1',
  status: 'succeeded',
  keywords: ['django'],
  sites: ['upwork'],
  startedAt: '2026-11-01T10:00:00+00:00',
  finishedAt: '2026-11-01T10:01:00+00:00',
  jobCount: 4,
  errorCount: 0,
  error: null,
  discordStatus: null,
  discordSent: 0,
  discordFailed: 0,
  discordError: null,
}

const SETTINGS: DiscordSettings = {
  isConfigured: true,
  tokenHint: '••••1234',
  defaultChannelId: '12345678901234567',
  mentionUserId: null,
  messageTemplate: '{title}',
  maxChars: 1900,
  updatedAt: null,
}

const CONFIG_SNAPSHOT: ConfigSnapshot = {
  values: {
    keywords: ['django'],
    limit: 3,
    maxAgeHours: 72,
    filter: EMPTY_FILTER,
    defaultFields: ['title'],
    sites: [],
  },
  version: 4,
  updatedAt: '2026-11-02T01:00:00+00:00',
  updatedBy: 'ui',
  isStale: false,
  jobFields: ['site', 'title', 'company'],
  mandatoryFields: ['site', 'company'],
  locationOptions: {},
}

const PAGE_STUBS = {
  RouterLink: RouterLinkStub,
  RunConfigSection: { template: '<section id="config"><h3>Config</h3></section>' },
}

class FakeEventSource {
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  close = vi.fn<() => void>()
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve: (value: T) => void = () => undefined
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function mountPage() {
  return mount(RunsPage, {
    global: { plugins: [createPinia()], stubs: PAGE_STUBS },
    attachTo: document.body,
  })
}

function historyRows(wrapper: ReturnType<typeof mountPage>) {
  const history = wrapper
    .findAll('section')
    .find((section) => section.get('h3').text() === 'History')
  return history?.findAll('li button') ?? []
}

function keywordInput(wrapper: ReturnType<typeof mountPage>): HTMLInputElement {
  return wrapper.get('#run-keywords').element as HTMLInputElement
}

describe('RunsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.stubGlobal('EventSource', FakeEventSource)
    provideRunUseCases({ getOptions, getRun, listRuns, startRun })
    provideDiscordUseCases({
      getSettings,
      saveSettings: { execute: vi.fn() },
      testConnection: { execute: vi.fn() },
      listChannels: { execute: vi.fn() },
      previewMessage: { execute: vi.fn() },
      sendMessage: { execute: vi.fn() },
    })
    getSettings.execute.mockResolvedValue(SETTINGS)
    vi.stubGlobal('localStorage', createMemoryStorage())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.innerHTML = ''
  })

  it('shows skeletons for the form and history until the first load finishes', async () => {
    const options = deferred<RunOptions>()
    getOptions.execute.mockReturnValue(options.promise)
    listRuns.execute.mockResolvedValue([RUN])
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('Loading run options')
    expect(wrapper.text()).toContain('Loading run history')
    expect(wrapper.find('#run-keywords').exists()).toBe(false)

    options.resolve(OPTIONS)
    await flushPromises()

    expect(wrapper.text()).not.toContain('Loading run options')
    expect(keywordInput(wrapper).value).toBe('')
    expect(historyRows(wrapper)).toHaveLength(1)
  })

  it('keeps typed keywords and the history on screen while it loads again', async () => {
    getOptions.execute.mockResolvedValueOnce(OPTIONS)
    listRuns.execute.mockResolvedValueOnce([RUN])
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.get('#run-keywords').setValue('django, vue')

    getOptions.execute.mockReturnValueOnce(deferred<RunOptions>().promise)
    listRuns.execute.mockReturnValueOnce(deferred<RunRecord[]>().promise)
    void useRunStore().load()
    await flushPromises()

    expect(wrapper.text()).not.toContain('Loading run options')
    expect(wrapper.text()).not.toContain('Loading run history')
    expect(keywordInput(wrapper).value).toBe('django, vue')
    expect(historyRows(wrapper)).toHaveLength(1)
  })

  it('shows a load error inside the start card and keeps the live log', async () => {
    getOptions.execute.mockRejectedValue(new Error('Scraper down'))
    listRuns.execute.mockResolvedValue([])
    const wrapper = mountPage()
    await flushPromises()

    const alert = wrapper.get('[role="alert"]')
    expect(alert.text()).toContain('Could not load runs')
    expect(alert.text()).toContain('Scraper down')
    expect(wrapper.find('[role="log"]').exists()).toBe(true)
  })

  it('loads again when Try again is pressed after an error', async () => {
    getOptions.execute.mockRejectedValueOnce(new Error('Scraper down')).mockResolvedValue(OPTIONS)
    listRuns.execute.mockResolvedValue([])
    const wrapper = mountPage()
    await flushPromises()

    const retry = wrapper.findAll('button').find((button) => button.text() === 'Try again')!
    await retry.trigger('click')
    await flushPromises()

    expect(getOptions.execute).toHaveBeenCalledTimes(2)
    expect(keywordInput(wrapper).value).toBe('')
  })

  it('orders the sections: start a run, config, results, history, live logs', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    listRuns.execute.mockResolvedValue([RUN])
    getRun.execute.mockResolvedValue({
      record: RUN,
      jobs: [],
      failures: [],
      payloads: [],
    } satisfies RunDetail)
    const wrapper = mountPage()
    await flushPromises()
    await historyRows(wrapper)[0]!.trigger('click')
    await flushPromises()

    const headings = wrapper.findAll('section h3').map((heading) => heading.text())

    expect(headings).toEqual(['Start a run', 'Config', 'Results', 'History', 'Live logs'])
  })

  it('puts the live logs last while no run is selected', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    listRuns.execute.mockResolvedValue([RUN])
    const wrapper = mountPage()
    await flushPromises()

    const headings = wrapper.findAll('section h3').map((heading) => heading.text())

    expect(headings).toEqual(['Start a run', 'Config', 'History', 'Live logs'])
  })

  it('puts the config card right below the start card as the config anchor', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    listRuns.execute.mockResolvedValue([])
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.find('#config').exists()).toBe(true)
  })

  it('blocks Run scrape while the config has unsaved changes', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    listRuns.execute.mockResolvedValue([])
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.get('#run-keywords').setValue('django')

    const config = useConfigStore()
    config.snapshot = CONFIG_SNAPSHOT
    config.values = { ...structuredClone(CONFIG_SNAPSHOT.values), limit: 9 }
    await nextTick()

    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Save or discard config changes first')

    config.discard()
    await nextTick()

    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })

  describe('discord send', () => {
    function notifyBox(wrapper: ReturnType<typeof mountPage>) {
      return wrapper.get('#run-notify-discord')
    }

    async function startWith(wrapper: ReturnType<typeof mountPage>) {
      await wrapper.get('#run-keywords').setValue('django')
      await wrapper.get('form').trigger('submit')
      await flushPromises()
    }

    it('enables the toggle when a default channel is set', async () => {
      getOptions.execute.mockResolvedValue(OPTIONS)
      listRuns.execute.mockResolvedValue([])
      const wrapper = mountPage()
      await flushPromises()

      expect(getSettings.execute).toHaveBeenCalledTimes(1)
      expect(notifyBox(wrapper).attributes('disabled')).toBeUndefined()
    })

    it.each<[string, DiscordSettings, string]>([
      [
        'no default channel',
        { ...SETTINGS, defaultChannelId: null },
        'Set a default channel on the Discord page',
      ],
      [
        'no bot token',
        { ...SETTINGS, isConfigured: false },
        'Save a bot token on the Discord page',
      ],
    ])('disables the toggle with %s and says what to do', async (_label, settings, hint) => {
      getSettings.execute.mockResolvedValue(settings)
      getOptions.execute.mockResolvedValue(OPTIONS)
      listRuns.execute.mockResolvedValue([])
      const wrapper = mountPage()
      await flushPromises()

      expect(notifyBox(wrapper).attributes('disabled')).toBeDefined()
      expect(wrapper.text()).toContain(hint)
    })

    it('disables the toggle without a hint while the settings load', async () => {
      getSettings.execute.mockReturnValue(deferred<DiscordSettings>().promise)
      getOptions.execute.mockResolvedValue(OPTIONS)
      listRuns.execute.mockResolvedValue([])
      const wrapper = mountPage()
      await flushPromises()

      expect(notifyBox(wrapper).attributes('disabled')).toBeDefined()
      expect(wrapper.find('[data-slot="discord-hint"]').exists()).toBe(false)
    })

    it('disables the toggle and says so when the settings cannot be loaded', async () => {
      getSettings.execute.mockRejectedValue(new Error('down'))
      getOptions.execute.mockResolvedValue(OPTIONS)
      listRuns.execute.mockResolvedValue([])
      const wrapper = mountPage()
      await flushPromises()

      expect(notifyBox(wrapper).attributes('disabled')).toBeDefined()
      expect(wrapper.text()).toContain('Could not load Discord settings')
    })

    it('starts the run with the toggle choice', async () => {
      getOptions.execute.mockResolvedValue(OPTIONS)
      listRuns.execute.mockResolvedValue([])
      startRun.execute.mockResolvedValue({ ...RUN, status: 'running' })
      const wrapper = mountPage()
      await flushPromises()
      await notifyBox(wrapper).trigger('click')

      await startWith(wrapper)

      expect(startRun.execute).toHaveBeenCalledWith(['django'], ['upwork'], true)
    })

    it('starts the run without a send when the toggle is off', async () => {
      getOptions.execute.mockResolvedValue(OPTIONS)
      listRuns.execute.mockResolvedValue([])
      startRun.execute.mockResolvedValue({ ...RUN, status: 'running' })
      const wrapper = mountPage()
      await flushPromises()

      await startWith(wrapper)

      expect(startRun.execute).toHaveBeenCalledWith(['django'], ['upwork'], false)
    })

    it.each<[RunRecord['discordStatus'], keyof typeof toast, string]>([
      ['sent', 'success', 'Sent 2 to Discord'],
      ['partial', 'warning', 'Sent 2, failed 1 on Discord'],
      ['failed', 'error', 'Discord failed: Missing access'],
    ])('toasts when sending ends as %s', async (final, kind, message) => {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
      try {
        getOptions.execute.mockResolvedValue(OPTIONS)
        listRuns.execute.mockResolvedValue([])
        startRun.execute.mockResolvedValue({ ...RUN, status: 'running', discordStatus: 'sending' })
        getRun.execute.mockResolvedValue({
          record: {
            ...RUN,
            discordStatus: final,
            discordSent: 2,
            discordFailed: final === 'partial' ? 1 : 0,
            discordError: final === 'failed' ? 'Missing access' : null,
          },
          jobs: [],
          failures: [],
          payloads: [],
        } satisfies RunDetail)
        const wrapper = mountPage()
        await flushPromises()
        await notifyBox(wrapper).trigger('click')
        await startWith(wrapper)

        await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

        expect(toast[kind]).toHaveBeenCalledWith(message)
      } finally {
        vi.useRealTimers()
      }
    })

    it('does not toast for a run without a send', async () => {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
      try {
        getOptions.execute.mockResolvedValue(OPTIONS)
        listRuns.execute.mockResolvedValue([])
        startRun.execute.mockResolvedValue({ ...RUN, status: 'running' })
        getRun.execute.mockResolvedValue({ record: RUN, jobs: [], failures: [], payloads: [] })
        const wrapper = mountPage()
        await flushPromises()
        await startWith(wrapper)

        await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)

        expect(toast.success).not.toHaveBeenCalled()
        expect(toast.warning).not.toHaveBeenCalled()
        expect(toast.error).not.toHaveBeenCalled()
      } finally {
        vi.useRealTimers()
      }
    })
  })
})
