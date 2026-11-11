import type { DiscordRemoteDataSource } from '@/modules/discord/data/datasources/DiscordRemoteDataSource'
import {
  toDiscordBot,
  toDiscordChannels,
  toDiscordContentModel,
  toDiscordMessages,
  toDiscordSendResult,
  toDiscordSettings,
  toDiscordSettingsChangesModel,
} from '@/modules/discord/data/models/DiscordModel'
import type {
  DiscordBot,
  DiscordChannel,
  DiscordContent,
  DiscordSendResult,
  DiscordSettings,
  DiscordSettingsChanges,
} from '@/modules/discord/domain/entities/Discord'
import type { DiscordRepository } from '@/modules/discord/domain/repositories/DiscordRepository'

export class DiscordRepositoryImpl implements DiscordRepository {
  private readonly dataSource: DiscordRemoteDataSource

  constructor(dataSource: DiscordRemoteDataSource) {
    this.dataSource = dataSource
  }

  async getSettings(): Promise<DiscordSettings> {
    return toDiscordSettings(await this.dataSource.getSettings())
  }

  async saveSettings(changes: DiscordSettingsChanges): Promise<DiscordSettings> {
    return toDiscordSettings(
      await this.dataSource.saveSettings(toDiscordSettingsChangesModel(changes)),
    )
  }

  async testConnection(): Promise<DiscordBot> {
    return toDiscordBot(await this.dataSource.testConnection())
  }

  async listChannels(): Promise<DiscordChannel[]> {
    return toDiscordChannels(await this.dataSource.listChannels())
  }

  async previewMessage(mention: boolean, content: DiscordContent): Promise<string[]> {
    return toDiscordMessages(
      await this.dataSource.previewMessage(mention, toDiscordContentModel(content)),
    )
  }

  async sendMessage(
    channelId: string,
    mention: boolean,
    content: DiscordContent,
  ): Promise<DiscordSendResult> {
    return toDiscordSendResult(
      await this.dataSource.sendMessage(channelId, mention, toDiscordContentModel(content)),
    )
  }
}
