import type { RouteRecordRaw } from 'vue-router'
import { httpClient } from '@/core/http/httpClient'
import { DiscordRemoteDataSource } from '@/modules/discord/data/datasources/DiscordRemoteDataSource'
import { DiscordRepositoryImpl } from '@/modules/discord/data/repositories/DiscordRepositoryImpl'
import { GetDiscordSettingsUseCase } from '@/modules/discord/domain/usecases/GetDiscordSettingsUseCase'
import { ListDiscordChannelsUseCase } from '@/modules/discord/domain/usecases/ListDiscordChannelsUseCase'
import { PreviewDiscordMessageUseCase } from '@/modules/discord/domain/usecases/PreviewDiscordMessageUseCase'
import { SaveDiscordSettingsUseCase } from '@/modules/discord/domain/usecases/SaveDiscordSettingsUseCase'
import { SendDiscordMessageUseCase } from '@/modules/discord/domain/usecases/SendDiscordMessageUseCase'
import { TestDiscordConnectionUseCase } from '@/modules/discord/domain/usecases/TestDiscordConnectionUseCase'
import { provideDiscordUseCases } from '@/modules/discord/presentation/stores/discordUseCases'

const repository = new DiscordRepositoryImpl(new DiscordRemoteDataSource(httpClient))

provideDiscordUseCases({
  getSettings: new GetDiscordSettingsUseCase(repository),
  saveSettings: new SaveDiscordSettingsUseCase(repository),
  testConnection: new TestDiscordConnectionUseCase(repository),
  listChannels: new ListDiscordChannelsUseCase(repository),
  previewMessage: new PreviewDiscordMessageUseCase(repository),
  sendMessage: new SendDiscordMessageUseCase(repository),
})

export const discordRoutes: RouteRecordRaw[] = [
  {
    path: '/discord',
    redirect: { path: '/', hash: '#discord' },
  },
]
