import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { ConfigSnapshot } from '@/modules/config/domain/entities/ScraperConfig'
import { provideConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'

const getConfig = { execute: vi.fn() }
const saveConfig = { execute: vi.fn() }

const SNAPSHOT: ConfigSnapshot = {
  values: { keywords: ['django'], limit: 3, maxAgeHours: 72, proxyUrl: null, sites: [] },
  isReadOnly: false,
  locked: [],
  isStale: false,
}

describe('useConfigStore', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    provideConfigUseCases({ getConfig, saveConfig })
  })

  it('loads a copy of the values', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    const store = useConfigStore()

    await store.load()

    expect(store.status).toBe('ready')
    expect(store.values).toEqual(SNAPSHOT.values)
    expect(store.values).not.toBe(SNAPSHOT.values)
  })

  it('shows an error when load fails', async () => {
    getConfig.execute.mockRejectedValue(new Error('Scraper down'))
    const store = useConfigStore()

    await store.load()

    expect(store.status).toBe('error')
    expect(store.errorMessage).toBe('Scraper down')
  })

  it('saves changed values then reloads', async () => {
    getConfig.execute.mockResolvedValue(SNAPSHOT)
    saveConfig.execute.mockResolvedValue(undefined)
    const store = useConfigStore()
    await store.load()
    store.values!.limit = 9

    await expect(store.save()).resolves.toBe(true)

    expect(saveConfig.execute).toHaveBeenCalledWith({ limit: 9 })
    expect(getConfig.execute).toHaveBeenCalledTimes(2)
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

  it('does not save read-only config', async () => {
    getConfig.execute.mockResolvedValue({ ...SNAPSHOT, isReadOnly: true })
    const store = useConfigStore()
    await store.load()

    await expect(store.save()).resolves.toBe(false)

    expect(saveConfig.execute).not.toHaveBeenCalled()
  })
})
