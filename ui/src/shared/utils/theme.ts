export const THEME_MODES = ['light', 'dark', 'system'] as const

export type ThemeMode = (typeof THEME_MODES)[number]
export type ResolvedTheme = 'light' | 'dark'

export const DEFAULT_THEME_MODE: ThemeMode = 'system'
export const THEME_STORAGE_KEY = 'scraper:theme'

export const THEME_MODE_LABELS: Record<ThemeMode, string> = {
  light: 'Light',
  dark: 'Dark',
  system: 'System',
}

export function isThemeMode(value: unknown): value is ThemeMode {
  return THEME_MODES.some((mode) => mode === value)
}

export function resolveTheme(mode: ThemeMode, isSystemDark: boolean): ResolvedTheme {
  if (mode === 'system') {
    return isSystemDark ? 'dark' : 'light'
  }
  return mode
}
