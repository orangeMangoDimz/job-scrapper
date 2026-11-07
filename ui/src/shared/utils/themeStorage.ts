import {
  DEFAULT_THEME_MODE,
  isThemeMode,
  THEME_STORAGE_KEY,
  type ThemeMode,
} from '@/shared/utils/theme'

export type ThemeStorage = Pick<Storage, 'getItem' | 'setItem'>

function browserStorage(): ThemeStorage {
  return window.localStorage
}

export function readThemeMode(getStorage: () => ThemeStorage = browserStorage): ThemeMode {
  try {
    const stored = getStorage().getItem(THEME_STORAGE_KEY)
    return isThemeMode(stored) ? stored : DEFAULT_THEME_MODE
  } catch {
    return DEFAULT_THEME_MODE
  }
}

export function writeThemeMode(
  mode: ThemeMode,
  getStorage: () => ThemeStorage = browserStorage,
): boolean {
  try {
    getStorage().setItem(THEME_STORAGE_KEY, mode)
    return true
  } catch {
    return false
  }
}
