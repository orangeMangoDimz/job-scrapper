import {
  browserStorage,
  readStorageItem,
  writeStorageItem,
  type KeyValueStorage,
} from '@/shared/utils/browserStorage'
import {
  DEFAULT_THEME_MODE,
  isThemeMode,
  THEME_STORAGE_KEY,
  type ThemeMode,
} from '@/shared/utils/theme'

export type ThemeStorage = KeyValueStorage

export function readThemeMode(getStorage: () => ThemeStorage = browserStorage): ThemeMode {
  const stored = readStorageItem(THEME_STORAGE_KEY, getStorage)
  return isThemeMode(stored) ? stored : DEFAULT_THEME_MODE
}

export function writeThemeMode(
  mode: ThemeMode,
  getStorage: () => ThemeStorage = browserStorage,
): boolean {
  return writeStorageItem(THEME_STORAGE_KEY, mode, getStorage)
}
