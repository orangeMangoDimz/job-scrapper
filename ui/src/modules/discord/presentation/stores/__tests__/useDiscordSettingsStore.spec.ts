import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { DiscordSettings } from '@/modules/discord/domain/entities/Discord'
import { provideDiscordUseCases } from '@/modules/discord/presentation/stores/discordUseCases'
import { useDiscordSettingsStore } from '@/modules/discord/presentation/stores/useDiscordSettingsStore'

const getSettings = { execute: vi.fn() }
const saveSettings = { execute: vi.fn() }
const testConnection = { execute: vi.fn() }
const listChannels = { execute: vi.fn() }
const previewMessage = { execute: vi.fn() }
const sendMessage = { execute: vi.fn() }

const SETTINGS: DiscordSettings = {
  isConfigured: true,
  tokenHint: '••••1234',
  defaultChannelId: '12345678901234567',
  mentionUserId: null,
  messageTemplate: '{title}',
  maxChars: 1900,
  updatedAt: null,
}

describe('useDiscordSettingsStore', () => {
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
  })

  it('loads the settings', async () => {
    getSettings.execute.mockResolvedValue(SETTINGS)
    const store = useDiscordSettingsStore()

    await store.load()

    expect(store.status).toBe('ready')
    expect(store.settings).toEqual(SETTINGS)
  })

  it('shows an error when load fails', async () => {
    getSettings.execute.mockRejectedValue(new Error('Scraper down'))
    const store = useDiscordSettingsStore()

    await store.load()

    expect(store.status).toBe('error')
    expect(store.errorMessage).toBe('Scraper down')
    expect(store.settings).toBeNull()
  })

  it('saves the changes and keeps the settings that come back', async () => {
    const saved = { ...SETTINGS, maxChars: 1500 }
    saveSettings.execute.mockResolvedValue(saved)
    const store = useDiscordSettingsStore()

    await expect(store.save({ maxChars: 1500 })).resolves.toBe(true)

    expect(saveSettings.execute).toHaveBeenCalledWith({ maxChars: 1500 })
    expect(store.settings).toEqual(saved)
    expect(store.saveError).toBeNull()
    expect(store.isSaving).toBe(false)
  })

  it('forgets an earlier bot name after a save', async () => {
    getSettings.execute.mockResolvedValue(SETTINGS)
    testConnection.execute.mockResolvedValue({ name: 'Jobs', id: '42' })
    saveSettings.execute.mockResolvedValue(SETTINGS)
    const store = useDiscordSettingsStore()
    await store.testConnection()

    await store.save({ token: 'new' })

    expect(store.bot).toBeNull()
  })

  it('keeps the message when save fails', async () => {
    saveSettings.execute.mockRejectedValue(new Error('Invalid channel id'))
    const store = useDiscordSettingsStore()

    await expect(store.save({ defaultChannelId: 'x' })).resolves.toBe(false)

    expect(store.saveError).toBe('Invalid channel id')
    expect(store.isSaving).toBe(false)
  })

  it('keeps the bot name when the test works', async () => {
    testConnection.execute.mockResolvedValue({ name: 'Jobs', id: '42' })
    const store = useDiscordSettingsStore()

    await expect(store.testConnection()).resolves.toBe(true)

    expect(store.bot).toEqual({ name: 'Jobs', id: '42' })
    expect(store.testError).toBeNull()
    expect(store.isTesting).toBe(false)
  })

  it('keeps the message when the test fails', async () => {
    testConnection.execute.mockRejectedValue(new Error('Discord rejected the bot token.'))
    const store = useDiscordSettingsStore()

    await expect(store.testConnection()).resolves.toBe(false)

    expect(store.bot).toBeNull()
    expect(store.testError).toBe('Discord rejected the bot token.')
    expect(store.isTesting).toBe(false)
  })

  it('clears an earlier test error when a new test works', async () => {
    testConnection.execute
      .mockRejectedValueOnce(new Error('Nope'))
      .mockResolvedValueOnce({ name: 'Jobs', id: '42' })
    const store = useDiscordSettingsStore()
    await store.testConnection()

    await store.testConnection()

    expect(store.testError).toBeNull()
  })
})
