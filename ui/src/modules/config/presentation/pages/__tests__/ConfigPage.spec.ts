import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'

import { EMPTY_FILTER, type ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
import ConfigPage from '@/modules/config/presentation/pages/ConfigPage.vue'
import { provideConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'

const getConfig = { execute: vi.fn() }
const saveConfig = { execute: vi.fn() }
const getConfigHistory = { execute: vi.fn() }
const restoreConfig = { execute: vi.fn() }

const SNAPSHOT: ConfigSnapshot = {
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
  jobFields: ['site', 'title', 'company', 'salary_min', 'company_id'],
  mandatoryFields: ['site', 'company'],
}

const VERSION = {
  version: 3,
  updatedAt: '2026-11-01T01:00:00+00:00',
  updatedBy: 'seed',
  keywords: ['django'],
  enabledSites: ['upwork'],
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve: (value: T) => void = () => undefined
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function mountPage() {
  return mount(ConfigPage, { global: { plugins: [createPinia()] }, attachTo: document.body })
}

function hasPageSkeleton(wrapper: ReturnType<typeof mountPage>): boolean {
  return wrapper.find('[data-slot="page-skeleton"]').exists()
}

describe('ConfigPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    getConfigHistory.execute.mockResolvedValue([VERSION])
    provideConfigUseCases({ getConfig, saveConfig, getConfigHistory, restoreConfig })
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('shows the page skeleton until the first load finishes', async () => {
    const first = deferred<ConfigSnapshot>()
    getConfig.execute.mockReturnValue(first.promise)
    const wrapper = mountPage()
    await flushPromises()

    expect(hasPageSkeleton(wrapper)).toBe(true)
    expect(wrapper.find('form').exists()).toBe(false)

    first.resolve(SNAPSHOT)
    await flushPromises()

    expect(hasPageSkeleton(wrapper)).toBe(false)
    expect(wrapper.find('form').exists()).toBe(true)
  })

  it('shows the job fields from the scraper as checkboxes', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const wrapper = mountPage()
    await flushPromises()

    const labels = wrapper.findAll('fieldset fieldset label').map((label) => label.text())
    expect(labels).toEqual(['Site', 'Title', 'Company', 'Salary min', 'Company ID'])
    expect(wrapper.get('#default-field-company').attributes('disabled')).toBeDefined()
    expect(wrapper.get('#default-field-title').attributes('data-state')).toBe('checked')
    expect(wrapper.get('#default-field-salary_min').attributes('data-state')).toBe('unchecked')
  })

  it('keeps the form and save bar on screen while a save reloads the config', async () => {
    const reload = deferred<ConfigSnapshot>()
    getConfig.execute.mockResolvedValueOnce(SNAPSHOT).mockReturnValueOnce(reload.promise)
    saveConfig.execute.mockResolvedValue(undefined)
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('#limit').setValue('5')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveConfig.execute).toHaveBeenCalledTimes(1)
    expect(hasPageSkeleton(wrapper)).toBe(false)
    expect(wrapper.find('#limit').exists()).toBe(true)
    expect(wrapper.find('[data-slot="save-bar"]').exists()).toBe(true)

    reload.resolve({ ...SNAPSHOT, version: 5, values: { ...SNAPSHOT.values, limit: 5 } })
    await flushPromises()

    expect((wrapper.get('#limit').element as HTMLInputElement).value).toBe('5')
  })

  it('keeps the older versions on screen while a restore reloads the config', async () => {
    const reload = deferred<ConfigSnapshot>()
    getConfig.execute.mockResolvedValueOnce(SNAPSHOT).mockReturnValueOnce(reload.promise)
    restoreConfig.execute.mockResolvedValue(undefined)
    const wrapper = mountPage()
    await flushPromises()

    const restore = wrapper.findAll('button').find((button) => button.text() === 'Restore')!
    await restore.trigger('click')
    const confirm = wrapper.findAll('button').find((button) => button.text() === 'Confirm restore')!
    await confirm.trigger('click')
    await flushPromises()

    expect(restoreConfig.execute).toHaveBeenCalledWith(3, 4)
    expect(hasPageSkeleton(wrapper)).toBe(false)
    expect(wrapper.text()).toContain('Version 3')
  })
})
