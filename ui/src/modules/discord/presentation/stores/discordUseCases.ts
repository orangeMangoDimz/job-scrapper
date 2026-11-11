import type { GetDiscordSettingsUseCase } from '@/modules/discord/domain/usecases/GetDiscordSettingsUseCase'
import type { ListDiscordChannelsUseCase } from '@/modules/discord/domain/usecases/ListDiscordChannelsUseCase'
import type { PreviewDiscordMessageUseCase } from '@/modules/discord/domain/usecases/PreviewDiscordMessageUseCase'
import type { SaveDiscordSettingsUseCase } from '@/modules/discord/domain/usecases/SaveDiscordSettingsUseCase'
import type { SendDiscordMessageUseCase } from '@/modules/discord/domain/usecases/SendDiscordMessageUseCase'
import type { TestDiscordConnectionUseCase } from '@/modules/discord/domain/usecases/TestDiscordConnectionUseCase'

export interface DiscordUseCases {
  getSettings: Pick<GetDiscordSettingsUseCase, 'execute'>
  saveSettings: Pick<SaveDiscordSettingsUseCase, 'execute'>
  testConnection: Pick<TestDiscordConnectionUseCase, 'execute'>
  listChannels: Pick<ListDiscordChannelsUseCase, 'execute'>
  previewMessage: Pick<PreviewDiscordMessageUseCase, 'execute'>
  sendMessage: Pick<SendDiscordMessageUseCase, 'execute'>
}

let useCases: DiscordUseCases | null = null

export function provideDiscordUseCases(next: DiscordUseCases): void {
  useCases = next
}

export function requireDiscordUseCases(): DiscordUseCases {
  if (useCases === null) {
    throw new Error('Discord use cases are not provided')
  }
  return useCases
}
