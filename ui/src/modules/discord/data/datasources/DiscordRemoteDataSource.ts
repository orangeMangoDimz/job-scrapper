import type { HttpClient } from '@/core/http/httpClient'
import type {
  DiscordBotModel,
  DiscordChannelsModel,
  DiscordContentModel,
  DiscordMessagesModel,
  DiscordSendResultModel,
  DiscordSettingsChangesModel,
  DiscordSettingsModel,
} from '@/modules/discord/data/models/DiscordModel'

const SETTINGS_PATH = '/discord/settings'
const TEST_PATH = '/discord/test'
const CHANNELS_PATH = '/discord/channels'
const PREVIEW_PATH = '/discord/preview'
const SEND_PATH = '/discord/send'

export const DISCORD_CALL_TIMEOUT_MS = 25_000
export const DISCORD_SEND_TIMEOUT_MS = 190_000

export class DiscordRemoteDataSource {
  private readonly client: HttpClient

  constructor(client: HttpClient) {
    this.client = client
  }

  getSettings(): Promise<DiscordSettingsModel> {
    return this.client.get<DiscordSettingsModel>(SETTINGS_PATH)
  }

  saveSettings(changes: DiscordSettingsChangesModel): Promise<DiscordSettingsModel> {
    return this.client.put<DiscordSettingsModel>(SETTINGS_PATH, changes)
  }

  testConnection(): Promise<DiscordBotModel> {
    return this.client.post<DiscordBotModel>(TEST_PATH, undefined, DISCORD_CALL_TIMEOUT_MS)
  }

  listChannels(): Promise<DiscordChannelsModel> {
    return this.client.get<DiscordChannelsModel>(CHANNELS_PATH, DISCORD_CALL_TIMEOUT_MS)
  }

  previewMessage(mention: boolean, content: DiscordContentModel): Promise<DiscordMessagesModel> {
    return this.client.post<DiscordMessagesModel>(PREVIEW_PATH, { mention, ...content })
  }

  sendMessage(
    channelId: string,
    mention: boolean,
    content: DiscordContentModel,
  ): Promise<DiscordSendResultModel> {
    return this.client.post<DiscordSendResultModel>(
      SEND_PATH,
      { channel_id: channelId, mention, ...content },
      DISCORD_SEND_TIMEOUT_MS,
    )
  }
}
