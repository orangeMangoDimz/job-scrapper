import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { createMemoryStorage } from '@/__tests__/memoryStorage'
import { EMPTY_FILTER, type ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
import { CONFIG_CARD_STORAGE_KEY } from '@/modules/config/presentation/components/configCardStorage'
import RunConfigSection from '@/modules/config/presentation/components/RunConfigSection.vue'
import { provideConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'

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
  jobFields: ['site', 'title', 'company'],
  mandatoryFields: ['site', 'company'],
  locationOptions: {},
}

function createTestRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
}

function mountSection(router: Router = createTestRouter()) {
  return mount(RunConfigSection, { global: { plugins: [router] }, attachTo: document.body })
}

function toggle(wrapper: ReturnType<typeof mountSection>) {
  return wrapper.get('button[aria-controls]')
}

describe('RunConfigSection', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.stubGlobal('localStorage', createMemoryStorage())
    setActivePinia(createPinia())
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    getConfigHistory.execute.mockResolvedValue([])
    provideConfigUseCases({ getConfig, saveConfig, getConfigHistory, restoreConfig })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('is a closed card titled Config by default', async () => {
    const wrapper = mountSection()
    await flushPromises()

    expect(wrapper.get('h3').text()).toBe('Config')
    expect(toggle(wrapper).attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('form').exists()).toBe(false)
  })

  it('opens when the page links to the config section', async () => {
    const router = createTestRouter()
    const wrapper = mountSection(router)
    await flushPromises()

    await router.push({ path: '/', hash: '#config' })
    await flushPromises()

    expect(toggle(wrapper).attributes('aria-expanded')).toBe('true')
    expect(localStorage.getItem(CONFIG_CARD_STORAGE_KEY)).toBe('true')
  })

  it('opens again on every link to the config section while the hash stays', async () => {
    const router = createTestRouter()
    const wrapper = mountSection(router)
    await flushPromises()
    await router.push({ path: '/', hash: '#config' })
    await flushPromises()
    await toggle(wrapper).trigger('click')
    expect(toggle(wrapper).attributes('aria-expanded')).toBe('false')

    await router.push({ path: '/', hash: '#config' })
    await flushPromises()

    expect(toggle(wrapper).attributes('aria-expanded')).toBe('true')
  })

  it('stays closed for links to other hashes', async () => {
    const router = createTestRouter()
    const wrapper = mountSection(router)
    await flushPromises()

    await router.push({ path: '/', hash: '#discord' })
    await flushPromises()

    expect(toggle(wrapper).attributes('aria-expanded')).toBe('false')
  })

  it('stops listening to links once unmounted', async () => {
    const router = createTestRouter()
    const wrapper = mountSection(router)
    await flushPromises()
    wrapper.unmount()

    await router.push({ path: '/', hash: '#config' })
    await flushPromises()

    expect(localStorage.getItem(CONFIG_CARD_STORAGE_KEY)).toBeNull()
  })

  it('shows the saved version under the title once loaded', async () => {
    const wrapper = mountSection()
    await flushPromises()

    expect(wrapper.text()).toContain('Version 4')
    expect(wrapper.text()).toContain('by ui')
    expect(wrapper.text()).toContain('Changes apply from the next run')
  })

  it('loads the config and its history once on mount', async () => {
    mountSection()
    await flushPromises()

    expect(getConfig.execute).toHaveBeenCalledTimes(1)
    expect(getConfigHistory.execute).toHaveBeenCalledTimes(1)
  })

  it('does not load again when the store already has the config', async () => {
    await useConfigStore().load()
    getConfig.execute.mockClear()
    getConfigHistory.execute.mockClear()

    mountSection()
    await flushPromises()

    expect(getConfig.execute).not.toHaveBeenCalled()
    expect(getConfigHistory.execute).not.toHaveBeenCalled()
  })

  it('shows the form once the card is opened', async () => {
    const wrapper = mountSection()
    await flushPromises()

    await toggle(wrapper).trigger('click')

    expect(toggle(wrapper).attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('form').exists()).toBe(true)
    expect(wrapper.find(`[id="${toggle(wrapper).attributes('aria-controls')}"]`).exists()).toBe(
      true,
    )
  })

  it('hides the form again when the card is closed', async () => {
    const wrapper = mountSection()
    await flushPromises()

    await toggle(wrapper).trigger('click')
    await toggle(wrapper).trigger('click')

    expect(wrapper.find('form').exists()).toBe(false)
  })

  it('keeps unsaved edits while the card is closed and opened again', async () => {
    const wrapper = mountSection()
    await flushPromises()
    await toggle(wrapper).trigger('click')
    await wrapper.get('#limit').setValue('9')

    await toggle(wrapper).trigger('click')
    await toggle(wrapper).trigger('click')

    expect((wrapper.get('#limit').element as HTMLInputElement).value).toBe('9')
    expect(useConfigStore().isDirty).toBe(true)
  })

  it('remembers open and closed in the browser', async () => {
    const wrapper = mountSection()
    await flushPromises()

    await toggle(wrapper).trigger('click')
    expect(window.localStorage.getItem(CONFIG_CARD_STORAGE_KEY)).toBe('true')

    await toggle(wrapper).trigger('click')
    expect(window.localStorage.getItem(CONFIG_CARD_STORAGE_KEY)).toBe('false')
  })

  it('starts open when it was left open', async () => {
    window.localStorage.setItem(CONFIG_CARD_STORAGE_KEY, 'true')

    const wrapper = mountSection()
    await flushPromises()

    expect(toggle(wrapper).attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('form').exists()).toBe(true)
  })

  it('still opens when the browser blocks storage', async () => {
    vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const wrapper = mountSection()
    await flushPromises()

    await toggle(wrapper).trigger('click')

    expect(wrapper.find('form').exists()).toBe(true)
  })

  it('shows a loading state inside the open card until the config arrives', async () => {
    window.localStorage.setItem(CONFIG_CARD_STORAGE_KEY, 'true')
    getConfig.execute.mockReturnValue(new Promise(() => undefined))

    const wrapper = mountSection()
    await flushPromises()

    expect(wrapper.find('[data-slot="page-skeleton"]').exists()).toBe(true)
    expect(wrapper.find('form').exists()).toBe(false)
  })

  it('shows the error and a retry inside the open card when the load fails', async () => {
    window.localStorage.setItem(CONFIG_CARD_STORAGE_KEY, 'true')
    getConfig.execute.mockRejectedValueOnce(new Error('Scraper down'))

    const wrapper = mountSection()
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Could not load config')
    expect(wrapper.text()).toContain('Scraper down')

    const retry = wrapper.findAll('button').find((button) => button.text() === 'Try again')!
    await retry.trigger('click')
    await flushPromises()

    expect(getConfig.execute).toHaveBeenCalledTimes(2)
    expect(wrapper.find('form').exists()).toBe(true)
  })

  it('keeps the save bar out of the page bottom', async () => {
    window.localStorage.setItem(CONFIG_CARD_STORAGE_KEY, 'true')

    const wrapper = mountSection()
    await flushPromises()

    expect(wrapper.get('[data-slot="save-bar"]').classes()).not.toContain('sticky')
  })
})
