import {
  browserStorage,
  readStorageFlag,
  writeStorageFlag,
  type KeyValueStorage,
} from '@/shared/utils/browserStorage'

export type NotifyDiscordStorage = KeyValueStorage

export const NOTIFY_DISCORD_STORAGE_KEY = 'scraper-ui:runs:notify-discord'

export function readNotifyDiscord(
  getStorage: () => NotifyDiscordStorage = browserStorage,
): boolean {
  return readStorageFlag(NOTIFY_DISCORD_STORAGE_KEY, getStorage)
}

export function writeNotifyDiscord(
  isEnabled: boolean,
  getStorage: () => NotifyDiscordStorage = browserStorage,
): void {
  writeStorageFlag(NOTIFY_DISCORD_STORAGE_KEY, isEnabled, getStorage)
}
