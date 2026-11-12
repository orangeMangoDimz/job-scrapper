import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import { EMPTY_FILTER, type ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
import ConfigForm from '@/modules/config/presentation/components/ConfigForm.vue'
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

async function mountForm(props: { isSaveBarSticky?: boolean } = {}, snapshot = SNAPSHOT) {
  getConfig.execute.mockResolvedValue(snapshot)
  const store = useConfigStore()
  await store.load()
  const wrapper = mount(ConfigForm, { props, attachTo: document.body })
  await flushPromises()
  return { wrapper, store }
}

function findButton(wrapper: Awaited<ReturnType<typeof mountForm>>['wrapper'], label: string) {
  return wrapper.findAll('button').find((button) => button.text() === label)
}

describe('ConfigForm', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    getConfigHistory.execute.mockResolvedValue([])
    provideConfigUseCases({ getConfig, saveConfig, getConfigHistory, restoreConfig })
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('keeps the field ids the config page always had', async () => {
    const { wrapper } = await mountForm()

    for (const id of [
      '#keywords',
      '#limit',
      '#max-age',
      '#global-location',
      '#default-field-title',
    ]) {
      expect(wrapper.find(id).exists(), id).toBe(true)
    }
  })

  it('renders nothing before the config is loaded', () => {
    const wrapper = mount(ConfigForm)

    expect(wrapper.find('form').exists()).toBe(false)
  })

  it('has Discard disabled until a value changes', async () => {
    const { wrapper } = await mountForm()
    const discard = findButton(wrapper, 'Discard')!

    expect(discard.attributes('disabled')).toBeDefined()

    await wrapper.get('#limit').setValue('9')

    expect(discard.attributes('disabled')).toBeUndefined()
  })

  it('puts the values back when Discard is pressed', async () => {
    const { wrapper, store } = await mountForm()
    await wrapper.get('#limit').setValue('9')

    await findButton(wrapper, 'Discard')!.trigger('click')

    expect(store.values?.limit).toBe(3)
    expect((wrapper.get('#limit').element as HTMLInputElement).value).toBe('3')
    expect(findButton(wrapper, 'Discard')!.attributes('disabled')).toBeDefined()
  })

  it('does not submit the form when Discard is pressed', async () => {
    const { wrapper } = await mountForm()
    await wrapper.get('#limit').setValue('9')

    await findButton(wrapper, 'Discard')!.trigger('click')

    expect(saveConfig.execute).not.toHaveBeenCalled()
  })

  it('disables Discard while a save is running', async () => {
    const { wrapper, store } = await mountForm()
    await wrapper.get('#limit').setValue('9')

    store.isSaving = true
    await flushPromises()

    expect(findButton(wrapper, 'Discard')!.attributes('disabled')).toBeDefined()
  })

  it('sticks the save bar to the page bottom by default', async () => {
    const { wrapper } = await mountForm()

    expect(wrapper.get('[data-slot="save-bar"]').classes()).toContain('sticky')
  })

  it('leaves the save bar in the flow when it is not sticky', async () => {
    const { wrapper } = await mountForm({ isSaveBarSticky: false })

    expect(wrapper.get('[data-slot="save-bar"]').classes()).not.toContain('sticky')
  })

  it('shows the busy notice and turns Save off when the scraper is stale', async () => {
    const { wrapper } = await mountForm({}, { ...SNAPSHOT, isStale: true })

    expect(wrapper.text()).toContain('The scraper is busy')
    expect(findButton(wrapper, 'Save')!.attributes('disabled')).toBeDefined()
  })

  it('shows the save error next to the buttons', async () => {
    const { wrapper, store } = await mountForm()

    store.saveError = 'Conflict'
    await flushPromises()

    expect(wrapper.get('[data-slot="save-bar"] [role="alert"]').text()).toBe('Conflict')
  })

  it('saves the changed values on submit', async () => {
    saveConfig.execute.mockResolvedValue(undefined)
    const { wrapper } = await mountForm()
    await wrapper.get('#limit').setValue('9')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveConfig.execute).toHaveBeenCalledWith({ limit: 9 }, 4)
  })
})
