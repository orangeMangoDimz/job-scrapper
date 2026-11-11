import type {
  DiscordBot,
  DiscordChannel,
  DiscordContent,
  DiscordSendResult,
  DiscordSettings,
  DiscordSettingsChanges,
} from '@/modules/discord/domain/entities/Discord'

export interface DiscordRepository {
  getSettings(): Promise<DiscordSettings>
  saveSettings(changes: DiscordSettingsChanges): Promise<DiscordSettings>
  testConnection(): Promise<DiscordBot>
  listChannels(): Promise<DiscordChannel[]>
  previewMessage(mention: boolean, content: DiscordContent): Promise<string[]>
  sendMessage(
    channelId: string,
    mention: boolean,
    content: DiscordContent,
  ): Promise<DiscordSendResult>
}
