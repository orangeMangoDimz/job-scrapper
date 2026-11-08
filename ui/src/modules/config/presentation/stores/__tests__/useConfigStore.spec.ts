import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { EMPTY_FILTER, type ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
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

describe('useConfigStore', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    getConfigHistory.execute.mockResolvedValue([])
    provideConfigUseCases({ getConfig, saveConfig, getConfigHistory, restoreConfig })
  })

  it('loads a copy of the values', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const store = useConfigStore()

    await store.load()

    expect(store.status).toBe('ready')
    expect(store.values).toEqual(SNAPSHOT.values)
    expect(store.values).not.toBe(SNAPSHOT.values)
    expect(store.values?.filter).not.toBe(SNAPSHOT.values.filter)
  })

  it('shows an error when load fails', async () => {
    getConfig.execute.mockRejectedValue(new Error('Scraper down'))
    const store = useConfigStore()

    await store.load()

    expect(store.status).toBe('error')
    expect(store.errorMessage).toBe('Scraper down')
  })

  it('saves changed values with the loaded version then reloads', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    saveConfig.execute.mockResolvedValue(undefined)
    const store = useConfigStore()
    await store.load()
    store.values!.limit = 9

    await expect(store.save()).resolves.toBe(true)

    expect(saveConfig.execute).toHaveBeenCalledWith({ limit: 9 }, 4)
    expect(getConfig.execute).toHaveBeenCalledTimes(2)
    expect(getConfigHistory.execute).toHaveBeenCalledTimes(1)
  })

  it('skips the save when nothing changed', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const store = useConfigStore()
    await store.load()

    await expect(store.save()).resolves.toBe(true)

    expect(saveConfig.execute).not.toHaveBeenCalled()
  })

  it('keeps the message when save fails', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    saveConfig.execute.mockRejectedValue(new Error('Bad config'))
    const store = useConfigStore()
    await store.load()
    store.values!.limit = 9

    await expect(store.save()).resolves.toBe(false)

    expect(store.saveError).toBe('Bad config')
  })

  it('does not save stale values', async () => {
    getConfig.execute.mockResolvedValue({ ...SNAPSHOT, isStale: true })
    const store = useConfigStore()
    await store.load()
    store.values!.limit = 9

    await expect(store.save()).resolves.toBe(false)

    expect(saveConfig.execute).not.toHaveBeenCalled()
  })

  it('loads history', async () => {
    getConfigHistory.execute.mockResolvedValue([VERSION])
    const store = useConfigStore()

    await store.loadHistory()

    expect(store.history).toEqual([VERSION])
  })

  it('shows an error when history fails', async () => {
    getConfigHistory.execute.mockRejectedValue(new Error('History down'))
    const store = useConfigStore()

    await store.loadHistory()

    expect(store.historyError).toBe('History down')
  })

  it('restores with the loaded version then reloads', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    restoreConfig.execute.mockResolvedValue(undefined)
    const store = useConfigStore()
    await store.load()

    await expect(store.restore(3)).resolves.toBe(true)

    expect(restoreConfig.execute).toHaveBeenCalledWith(3, 4)
    expect(getConfig.execute).toHaveBeenCalledTimes(2)
    expect(getConfigHistory.execute).toHaveBeenCalledTimes(1)
  })

  it('keeps the message when restore fails', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    restoreConfig.execute.mockRejectedValue(new Error('Conflict'))
    const store = useConfigStore()
    await store.load()

    await expect(store.restore(3)).resolves.toBe(false)

    expect(store.saveError).toBe('Conflict')
  })

  it('does not restore over stale values', async () => {
    getConfig.execute.mockResolvedValue({ ...SNAPSHOT, isStale: true })
    const store = useConfigStore()
    await store.load()

    await expect(store.restore(3)).resolves.toBe(false)

    expect(restoreConfig.execute).not.toHaveBeenCalled()
  })
})
