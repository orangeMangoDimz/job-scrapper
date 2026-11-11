import type {
  DiscordBot,
  DiscordChannel,
  DiscordContent,
  DiscordMessageKind,
  DiscordMessageResult,
  DiscordSendResult,
  DiscordSettings,
  DiscordSettingsChanges,
} from '@/modules/discord/domain/entities/Discord'

export interface DiscordSettingsModel {
  configured: boolean
  token_hint: string | null
  default_channel_id: string | null
  mention_user_id: string | null
  message_template: string
  max_chars: number
  updated_at: string | null
}

export interface DiscordSettingsChangesModel {
  token?: string
  default_channel_id?: string | null
  mention_user_id?: string | null
  message_template?: string
  max_chars?: number
}

export interface DiscordBotModel {
  bot_name: string
  bot_id: string
}

export interface DiscordChannelsModel {
  channels: {
    id: string
    name: string
    guild_id: string
    guild_name: string
  }[]
}

export type DiscordContentModel = { text: string } | { run_id: string; job_indexes: number[] }

export interface DiscordMessagesModel {
  messages: string[]
}

export interface DiscordMessageResultModel {
  index: number
  kind: DiscordMessageKind
  title: string | null
  status: 'sent' | 'failed'
  message_id: string | null
  error: string | null
}

export interface DiscordSendResultModel {
  sent: number
  failed: number
  results: DiscordMessageResultModel[]
}

export function toDiscordSettings(model: DiscordSettingsModel): DiscordSettings {
  return {
    isConfigured: model.configured,
    tokenHint: model.token_hint,
    defaultChannelId: model.default_channel_id,
    mentionUserId: model.mention_user_id,
    messageTemplate: model.message_template,
    maxChars: model.max_chars,
    updatedAt: model.updated_at,
  }
}

export function toDiscordSettingsChangesModel(
  changes: DiscordSettingsChanges,
): DiscordSettingsChangesModel {
  const { defaultChannelId, mentionUserId, messageTemplate, maxChars, ...shared } = changes
  return {
    ...shared,
    ...(defaultChannelId === undefined ? {} : { default_channel_id: defaultChannelId }),
    ...(mentionUserId === undefined ? {} : { mention_user_id: mentionUserId }),
    ...(messageTemplate === undefined ? {} : { message_template: messageTemplate }),
    ...(maxChars === undefined ? {} : { max_chars: maxChars }),
  }
}

export function toDiscordBot(model: DiscordBotModel): DiscordBot {
  return { name: model.bot_name, id: model.bot_id }
}

export function toDiscordChannels(model: DiscordChannelsModel): DiscordChannel[] {
  return model.channels.map((channel) => ({
    id: channel.id,
    name: channel.name,
    guildId: channel.guild_id,
    guildName: channel.guild_name,
  }))
}

export function toDiscordContentModel(content: DiscordContent): DiscordContentModel {
  return content.kind === 'text'
    ? { text: content.text }
    : { run_id: content.runId, job_indexes: content.jobIndexes }
}

export function toDiscordMessages(model: DiscordMessagesModel): string[] {
  return model.messages
}

function toDiscordMessageResult(model: DiscordMessageResultModel): DiscordMessageResult {
  return {
    index: model.index,
    kind: model.kind,
    title: model.title,
    status: model.status,
    messageId: model.message_id,
    error: model.error,
  }
}

export function toDiscordSendResult(model: DiscordSendResultModel): DiscordSendResult {
  return {
    sent: model.sent,
    failed: model.failed,
    results: model.results.map(toDiscordMessageResult),
  }
}
