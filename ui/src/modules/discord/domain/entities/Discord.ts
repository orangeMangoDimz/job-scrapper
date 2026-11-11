export const MAX_MESSAGE_CHARS = 2000
export const MAX_JOBS_PER_SEND = 50

export interface DiscordSettings {
  isConfigured: boolean
  tokenHint: string | null
  defaultChannelId: string | null
  mentionUserId: string | null
  messageTemplate: string
  maxChars: number
  updatedAt: string | null
}

export interface DiscordSettingsForm {
  token: string
  defaultChannelId: string
  mentionUserId: string
  messageTemplate: string
  maxChars: string
}

export interface DiscordSettingsChanges {
  token?: string
  defaultChannelId?: string | null
  mentionUserId?: string | null
  messageTemplate?: string
  maxChars?: number
}

export interface DiscordBot {
  name: string
  id: string
}

export interface DiscordChannel {
  id: string
  name: string
  guildId: string
  guildName: string
}

export type DiscordContent =
  { kind: 'text'; text: string } | { kind: 'jobs'; runId: string; jobIndexes: number[] }

export type DiscordMessageKind = 'text' | 'job' | 'summary'

export interface DiscordMessageResult {
  index: number
  kind: DiscordMessageKind
  title: string | null
  status: 'sent' | 'failed'
  messageId: string | null
  error: string | null
}

export interface DiscordSendResult {
  sent: number
  failed: number
  results: DiscordMessageResult[]
}

export function toSettingsForm(settings: DiscordSettings): DiscordSettingsForm {
  return {
    token: '',
    defaultChannelId: settings.defaultChannelId ?? '',
    mentionUserId: settings.mentionUserId ?? '',
    messageTemplate: settings.messageTemplate,
    maxChars: String(settings.maxChars),
  }
}

function toNullableId(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

export function toSettingsChanges(
  form: DiscordSettingsForm,
  settings: DiscordSettings,
): DiscordSettingsChanges {
  const token = form.token.trim()
  const defaultChannelId = toNullableId(form.defaultChannelId)
  const mentionUserId = toNullableId(form.mentionUserId)
  const maxChars = Number(form.maxChars)
  return {
    ...(token === '' ? {} : { token }),
    ...(defaultChannelId === settings.defaultChannelId ? {} : { defaultChannelId }),
    ...(mentionUserId === settings.mentionUserId ? {} : { mentionUserId }),
    ...(form.messageTemplate === settings.messageTemplate
      ? {}
      : { messageTemplate: form.messageTemplate }),
    ...(maxChars === settings.maxChars ? {} : { maxChars }),
  }
}

export function toMentionPrefix(userId: string | null, isMentioned: boolean): string {
  return isMentioned && userId !== null ? `<@${userId}>\n` : ''
}

export function countChars(text: string): number {
  return [...text].length
}

function pluralMessages(count: number): string {
  return count === 1 ? '1 message' : `${count} messages`
}

export function toSendSummary(result: DiscordSendResult): string {
  if (result.failed === 0) {
    return `Sent ${pluralMessages(result.sent)}`
  }
  if (result.sent === 0) {
    return `Nothing was sent, ${result.failed} failed`
  }
  return `Sent ${result.sent}, ${result.failed} failed`
}
