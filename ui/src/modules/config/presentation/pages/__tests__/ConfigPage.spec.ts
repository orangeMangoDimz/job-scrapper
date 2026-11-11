import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'

import { EMPTY_FILTER, type ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
import ConfigPage from '@/modules/config/presentation/pages/ConfigPage.vue'
import { provideConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'
import { provideDiscordUseCases } from '@/modules/discord/presentation/stores/discordUseCases'

const getConfig = { execute: vi.fn() }
const saveConfig = { execute: vi.fn() }
const getConfigHistory = { execute: vi.fn() }
const restoreConfig = { execute: vi.fn() }
const getDiscordSettings = { execute: vi.fn() }
const saveDiscordSettings = { execute: vi.fn() }
const testDiscordConnection = { execute: vi.fn() }
const listDiscordChannels = { execute: vi.fn() }
const previewDiscordMessage = { execute: vi.fn() }
const sendDiscordMessage = { execute: vi.fn() }

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
  locationOptions: {},
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

function findShowMoreToggle(wrapper: ReturnType<typeof mountPage>) {
  return wrapper.findAll('button').find((button) => /^Show (\d+ more|less)/.test(button.text()))
}

function hasPageSkeleton(wrapper: ReturnType<typeof mountPage>): boolean {
  return wrapper.find('[data-slot="page-skeleton"]').exists()
}

describe('ConfigPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    getConfigHistory.execute.mockResolvedValue([VERSION])
    provideConfigUseCases({ getConfig, saveConfig, getConfigHistory, restoreConfig })
    getDiscordSettings.execute.mockResolvedValue({
      isConfigured: true,
      tokenHint: '••••1234',
      defaultChannelId: null,
      mentionUserId: null,
      messageTemplate: '{title}',
      maxChars: 1900,
      updatedAt: null,
    })
    provideDiscordUseCases({
      getSettings: getDiscordSettings,
      saveSettings: saveDiscordSettings,
      testConnection: testDiscordConnection,
      listChannels: listDiscordChannels,
      previewMessage: previewDiscordMessage,
      sendMessage: sendDiscordMessage,
    })
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

  it('shows only the latest 3 older versions until Show more is pressed', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    getConfigHistory.execute.mockResolvedValue(
      [8, 7, 6, 5, 4].map((version) => ({ ...VERSION, version })),
    )
    const wrapper = mountPage()
    await flushPromises()
    const toggle = findShowMoreToggle(wrapper)!
    const versionRows = () => wrapper.findAll(`[id="${toggle.attributes('aria-controls')}"] li`)

    expect(versionRows()).toHaveLength(3)
    expect(wrapper.text()).toContain('Version 6')
    expect(wrapper.text()).not.toContain('Version 5')
    expect(toggle.text()).toContain('Show 2 more')

    await toggle.trigger('click')

    expect(versionRows()).toHaveLength(5)
    expect(toggle.text()).toContain('Show less')

    await toggle.trigger('click')

    expect(versionRows()).toHaveLength(3)
  })

  it('drops a pending restore when its row is collapsed away', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    getConfigHistory.execute.mockResolvedValue(
      [8, 7, 6, 5].map((version) => ({ ...VERSION, version })),
    )
    const wrapper = mountPage()
    await flushPromises()
    const toggle = findShowMoreToggle(wrapper)!

    await toggle.trigger('click')
    const restoreButtons = wrapper.findAll('button').filter((button) => button.text() === 'Restore')
    await restoreButtons[3]!.trigger('click')
    expect(wrapper.text()).toContain('Confirm restore')

    await toggle.trigger('click')
    await toggle.trigger('click')

    expect(wrapper.text()).not.toContain('Confirm restore')
  })

  it('hides the Show more toggle when there are 3 or fewer older versions', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const wrapper = mountPage()
    await flushPromises()

    expect(findShowMoreToggle(wrapper)).toBeUndefined()
  })

  it('shows a placeholder in each empty box of the global section', async () => {
    getConfig.execute.mockResolvedValue({
      ...SNAPSHOT,
      values: { ...SNAPSHOT.values, keywords: [], limit: null, maxAgeHours: null },
    })
    const wrapper = mountPage()
    await flushPromises()

    const hint = (id: string): string | undefined => wrapper.get(id).attributes('placeholder')
    expect(hint('#keywords')).toBe('Keywords')
    expect(hint('#limit')).toBe('Limit per site')
    expect(hint('#max-age')).toBe('Max job age in hours')
    expect(hint('#global-location')).toBe('Locations')
    expect(hint('#global-employment')).toBe('Employment types')
    expect(hint('#global-work')).toBe('Work types')
  })

  it('gives a site a city picker only when the scraper sent a city list for it', async () => {
    const api = { isEnabled: true, locations: [], isCountryWide: false, delaySeconds: null }
    const site = { isEnabled: true, limit: null, maxAgeHours: null, filter: null, fields: null }
    getConfig.execute.mockResolvedValue({
      ...SNAPSHOT,
      values: {
        ...SNAPSHOT.values,
        sites: [
          { ...site, name: 'glints', api },
          { ...site, name: 'upwork', api: { ...api, locations: ['Remote'] } },
        ],
      },
      locationOptions: { glints: [{ label: 'Jakarta', value: 'jakarta-id' }] },
    })
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe = vi.fn<ResizeObserver['observe']>()
        unobserve = vi.fn<ResizeObserver['unobserve']>()
        disconnect = vi.fn<ResizeObserver['disconnect']>()
      },
    )
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.find('#glints-api-locations').exists()).toBe(true)
    expect(wrapper.find('#upwork-api-locations').exists()).toBe(false)
    vi.unstubAllGlobals()
  })

  it('shows a Discord section with its own form, apart from the config form', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const wrapper = mountPage()
    await flushPromises()

    const forms = wrapper.findAll('form')
    expect(forms).toHaveLength(2)
    expect(forms[0]!.find('#discord-token').exists()).toBe(false)
    expect(forms[1]!.find('#discord-token').exists()).toBe(true)
    expect(forms[1]!.text()).toContain('Test connection')
  })

  it('saves Discord settings without saving the config', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    saveDiscordSettings.execute.mockResolvedValue({
      isConfigured: true,
      tokenHint: '••••1234',
      defaultChannelId: null,
      mentionUserId: null,
      messageTemplate: '{title}',
      maxChars: 1900,
      updatedAt: null,
    })
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.findAll('form')[1]!.trigger('submit')
    await flushPromises()

    expect(saveDiscordSettings.execute).toHaveBeenCalledTimes(1)
    expect(saveConfig.execute).not.toHaveBeenCalled()
  })
})
