import { describe, expect, it, vi } from 'vitest'
import type { DiscordRepository } from '@/modules/discord/domain/repositories/DiscordRepository'
import { GetDiscordSettingsUseCase } from '@/modules/discord/domain/usecases/GetDiscordSettingsUseCase'
import { ListDiscordChannelsUseCase } from '@/modules/discord/domain/usecases/ListDiscordChannelsUseCase'
import { PreviewDiscordMessageUseCase } from '@/modules/discord/domain/usecases/PreviewDiscordMessageUseCase'
import { SaveDiscordSettingsUseCase } from '@/modules/discord/domain/usecases/SaveDiscordSettingsUseCase'
import { SendDiscordMessageUseCase } from '@/modules/discord/domain/usecases/SendDiscordMessageUseCase'
import { TestDiscordConnectionUseCase } from '@/modules/discord/domain/usecases/TestDiscordConnectionUseCase'

function makeRepository(): DiscordRepository {
  return {
    getSettings: vi.fn().mockResolvedValue('settings'),
    saveSettings: vi.fn().mockResolvedValue('saved'),
    testConnection: vi.fn().mockResolvedValue('bot'),
    listChannels: vi.fn().mockResolvedValue('channels'),
    previewMessage: vi.fn().mockResolvedValue('messages'),
    sendMessage: vi.fn().mockResolvedValue('result'),
  } as unknown as DiscordRepository
}

describe('Discord use cases', () => {
  it('gets the settings', async () => {
    const repository = makeRepository()

    await expect(new GetDiscordSettingsUseCase(repository).execute()).resolves.toBe('settings')
  })

  it('saves the changes', async () => {
    const repository = makeRepository()

    await expect(new SaveDiscordSettingsUseCase(repository).execute({ maxChars: 5 })).resolves.toBe(
      'saved',
    )
    expect(repository.saveSettings).toHaveBeenCalledWith({ maxChars: 5 })
  })

  it('tests the connection', async () => {
    const repository = makeRepository()

    await expect(new TestDiscordConnectionUseCase(repository).execute()).resolves.toBe('bot')
  })

  it('lists the channels', async () => {
    const repository = makeRepository()

    await expect(new ListDiscordChannelsUseCase(repository).execute()).resolves.toBe('channels')
  })

  it('previews the content', async () => {
    const repository = makeRepository()
    const content = { kind: 'text' as const, text: 'hi' }

    await expect(new PreviewDiscordMessageUseCase(repository).execute(true, content)).resolves.toBe(
      'messages',
    )
    expect(repository.previewMessage).toHaveBeenCalledWith(true, content)
  })

  it('sends the content', async () => {
    const repository = makeRepository()
    const content = { kind: 'text' as const, text: 'hi' }

    await expect(
      new SendDiscordMessageUseCase(repository).execute('123', false, content),
    ).resolves.toBe('result')
    expect(repository.sendMessage).toHaveBeenCalledWith('123', false, content)
  })
})
