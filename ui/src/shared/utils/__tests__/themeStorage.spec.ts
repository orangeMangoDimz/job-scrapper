import { describe, expect, it, vi } from 'vitest'
import { createMemoryStorage } from '@/__tests__/memoryStorage'
import { THEME_STORAGE_KEY } from '@/shared/utils/theme'
import { readThemeMode, writeThemeMode, type ThemeStorage } from '@/shared/utils/themeStorage'

function memoryStorage(initial: Record<string, string> = {}): ThemeStorage & {
  values: Record<string, string>
} {
  const values = { ...initial }
  return {
    values,
    getItem: (key) => values[key] ?? null,
    setItem: (key, value) => {
      values[key] = value
    },
  }
}

const throwingStorage: ThemeStorage = {
  getItem: () => {
    throw new Error('blocked')
  },
  setItem: () => {
    throw new Error('blocked')
  },
}

describe('themeStorage', () => {
  it('reads a stored mode', () => {
    const storage = memoryStorage({ [THEME_STORAGE_KEY]: 'dark' })

    expect(readThemeMode(() => storage)).toBe('dark')
  })

  it('falls back to system when nothing is stored', () => {
    expect(readThemeMode(() => memoryStorage())).toBe('system')
  })

  it('falls back to system when the stored value is invalid', () => {
    expect(readThemeMode(() => memoryStorage({ [THEME_STORAGE_KEY]: 'sepia' }))).toBe('system')
  })

  it('falls back to system when storage throws', () => {
    expect(readThemeMode(() => throwingStorage)).toBe('system')
  })

  it('writes the mode under the theme key', () => {
    const storage = memoryStorage()

    expect(writeThemeMode('light', () => storage)).toBe(true)
    expect(storage.values[THEME_STORAGE_KEY]).toBe('light')
  })

  it('reports a failed write without throwing', () => {
    expect(writeThemeMode('dark', () => throwingStorage)).toBe(false)
  })

  it('uses window.localStorage by default', () => {
    vi.stubGlobal('localStorage', createMemoryStorage())

    writeThemeMode('dark')

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
    expect(readThemeMode()).toBe('dark')
    vi.unstubAllGlobals()
  })
})
