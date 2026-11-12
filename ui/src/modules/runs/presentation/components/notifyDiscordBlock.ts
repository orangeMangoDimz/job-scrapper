import type { DiscordSettings } from '@/modules/discord/domain/entities/Discord'
import type { LoadStatus } from '@/shared/utils/loadStatus'

export type NotifyDiscordBlock = 'loading' | 'load-failed' | 'not-configured' | 'no-channel'

export function toNotifyDiscordBlock(
  status: LoadStatus,
  settings: DiscordSettings | null,
): NotifyDiscordBlock | null {
  if (settings === null) {
    return status === 'error' ? 'load-failed' : 'loading'
  }
  if (!settings.isConfigured) {
    return 'not-configured'
  }
  return settings.defaultChannelId === null ? 'no-channel' : null
}
