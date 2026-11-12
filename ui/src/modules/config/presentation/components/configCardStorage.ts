import {
  browserStorage,
  readStorageFlag,
  writeStorageFlag,
  type KeyValueStorage,
} from '@/shared/utils/browserStorage'

export type ConfigCardStorage = KeyValueStorage

export const CONFIG_CARD_STORAGE_KEY = 'scraper-ui:runs:config-card-open'

export function readConfigCardOpen(getStorage: () => ConfigCardStorage = browserStorage): boolean {
  return readStorageFlag(CONFIG_CARD_STORAGE_KEY, getStorage)
}

export function writeConfigCardOpen(
  isOpen: boolean,
  getStorage: () => ConfigCardStorage = browserStorage,
): void {
  writeStorageFlag(CONFIG_CARD_STORAGE_KEY, isOpen, getStorage)
}
