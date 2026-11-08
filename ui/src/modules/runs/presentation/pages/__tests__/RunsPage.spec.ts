import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'

import type { RunDetail, RunOptions, RunRecord } from '@/modules/runs/domain/entities/Run'
import RunsPage from '@/modules/runs/presentation/pages/RunsPage.vue'
import { provideRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'
import { useRunStore } from '@/modules/runs/presentation/stores/useRunStore'

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
  return mount(RunsPage, { global: { plugins: [createPinia()] }, attachTo: document.body })
}

function historyRows(wrapper: ReturnType<typeof mountPage>) {
  const history = wrapper
    .findAll('section')
    .find((section) => section.get('h2').text() === 'History')
  return history?.findAll('li button') ?? []
}

function keywordInput(wrapper: ReturnType<typeof mountPage>): HTMLInputElement {
  return wrapper.get('#keywords').element as HTMLInputElement
}

describe('RunsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.stubGlobal('EventSource', FakeEventSource)
    provideRunUseCases({ getOptions, getRun, listRuns, startRun })
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
    expect(wrapper.find('#keywords').exists()).toBe(false)

    options.resolve(OPTIONS)
    await flushPromises()

    expect(wrapper.text()).not.toContain('Loading run options')
    expect(keywordInput(wrapper).value).toBe('django')
    expect(historyRows(wrapper)).toHaveLength(1)
  })

  it('keeps typed keywords and the history on screen while it loads again', async () => {
    getOptions.execute.mockResolvedValueOnce(OPTIONS)
    listRuns.execute.mockResolvedValueOnce([RUN])
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.get('#keywords').setValue('django, vue')

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
    expect(keywordInput(wrapper).value).toBe('django')
  })

  it('orders the sections: start a run, results, history, live logs', async () => {
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

    const headings = wrapper.findAll('section h2').map((heading) => heading.text())

    expect(headings).toEqual(['Start a run', 'Results', 'History', 'Live logs'])
  })

  it('puts the live logs last while no run is selected', async () => {
    getOptions.execute.mockResolvedValue(OPTIONS)
    listRuns.execute.mockResolvedValue([RUN])
    const wrapper = mountPage()
    await flushPromises()

    const headings = wrapper.findAll('section h2').map((heading) => heading.text())

    expect(headings).toEqual(['Start a run', 'History', 'Live logs'])
  })
})
