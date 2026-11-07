import { describe, expect, it } from 'vitest'
import {
  DEFAULT_THEME_MODE,
  isThemeMode,
  resolveTheme,
  THEME_MODE_LABELS,
  THEME_MODES,
} from '@/shared/utils/theme'

describe('theme', () => {
  it('defaults to following the system', () => {
    expect(DEFAULT_THEME_MODE).toBe('system')
  })

  it('labels every mode', () => {
    expect(THEME_MODES.map((mode) => THEME_MODE_LABELS[mode])).toEqual(['Light', 'Dark', 'System'])
  })

  it('accepts only known modes', () => {
    expect(THEME_MODES.every(isThemeMode)).toBe(true)
    expect(isThemeMode('sepia')).toBe(false)
    expect(isThemeMode(null)).toBe(false)
    expect(isThemeMode(undefined)).toBe(false)
    expect(isThemeMode('')).toBe(false)
  })

  it('resolves explicit modes regardless of the system', () => {
    expect(resolveTheme('light', true)).toBe('light')
    expect(resolveTheme('dark', false)).toBe('dark')
  })

  it('resolves system from the device preference', () => {
    expect(resolveTheme('system', true)).toBe('dark')
    expect(resolveTheme('system', false)).toBe('light')
  })
})
