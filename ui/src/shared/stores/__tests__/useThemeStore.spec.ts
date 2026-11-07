import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryStorage } from '@/__tests__/memoryStorage'
import { createPinia, setActivePinia } from 'pinia'
import { useThemeStore } from '@/shared/stores/useThemeStore'
import { THEME_STORAGE_KEY } from '@/shared/utils/theme'

type ChangeListener = (event: MediaQueryListEvent) => void

interface SystemScheme {
  setDark: (isDark: boolean) => void
  listenerCount: () => number
}

function stubSystemScheme(initialDark: boolean): SystemScheme {
  let isDark = initialDark
  const listeners = new Set<ChangeListener>()
  vi.stubGlobal('matchMedia', (query: string) => ({
    get matches() {
      return isDark
    },
    media: query,
    addEventListener: (_type: string, listener: ChangeListener) => listeners.add(listener),
    removeEventListener: (_type: string, listener: ChangeListener) => listeners.delete(listener),
  }))
  return {
    setDark(next) {
      isDark = next
      listeners.forEach((listener) => listener({ matches: next } as MediaQueryListEvent))
    },
    listenerCount: () => listeners.size,
  }
}

function attributeTheme(): string | undefined {
  return document.documentElement.dataset.theme
}

describe('useThemeStore', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createMemoryStorage())
    setActivePinia(createPinia())
    window.localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.style.colorScheme = ''
  })

  afterEach(() => {
    useThemeStore().dispose()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.style.colorScheme = ''
  })

  it('starts in system mode and resolves it from the device', () => {
    stubSystemScheme(true)
    const store = useThemeStore()

    store.init()

    expect(store.mode).toBe('system')
    expect(store.resolvedTheme).toBe('dark')
    expect(attributeTheme()).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')
  })

  it('resolves system to light on a light device', () => {
    stubSystemScheme(false)
    const store = useThemeStore()

    store.init()

    expect(store.resolvedTheme).toBe('light')
    expect(attributeTheme()).toBe('light')
    expect(document.documentElement.style.colorScheme).toBe('light')
  })

  it('restores the stored mode', () => {
    stubSystemScheme(false)
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    const store = useThemeStore()

    store.init()

    expect(store.mode).toBe('dark')
    expect(attributeTheme()).toBe('dark')
  })

  it('falls back to system when the stored value is invalid', () => {
    stubSystemScheme(true)
    window.localStorage.setItem(THEME_STORAGE_KEY, 'sepia')
    const store = useThemeStore()

    store.init()

    expect(store.mode).toBe('system')
    expect(attributeTheme()).toBe('dark')
  })

  it('falls back to system when storage cannot be read', () => {
    stubSystemScheme(true)
    vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const store = useThemeStore()

    store.init()

    expect(store.mode).toBe('system')
  })

  it('applies and persists an explicit mode', () => {
    stubSystemScheme(false)
    const store = useThemeStore()
    store.init()

    store.setMode('dark')

    expect(store.resolvedTheme).toBe('dark')
    expect(attributeTheme()).toBe('dark')
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
  })

  it('keeps the mode applied when persisting fails', () => {
    stubSystemScheme(false)
    vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const store = useThemeStore()
    store.init()

    store.setMode('dark')

    expect(attributeTheme()).toBe('dark')
  })

  it('ignores the device once a mode is chosen explicitly', () => {
    const system = stubSystemScheme(false)
    const store = useThemeStore()
    store.init()
    store.setMode('light')

    system.setDark(true)

    expect(store.resolvedTheme).toBe('light')
    expect(attributeTheme()).toBe('light')
  })

  it('follows live device changes in system mode', () => {
    const system = stubSystemScheme(false)
    const store = useThemeStore()
    store.init()

    system.setDark(true)
    expect(attributeTheme()).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')

    system.setDark(false)
    expect(attributeTheme()).toBe('light')
  })

  it('listens to the device only once however often it is initialised', () => {
    const system = stubSystemScheme(false)
    const store = useThemeStore()

    store.init()
    store.init()

    expect(system.listenerCount()).toBe(1)
  })

  it('stops listening to the device when disposed', () => {
    const system = stubSystemScheme(false)
    const store = useThemeStore()
    store.init()

    store.dispose()

    expect(system.listenerCount()).toBe(0)
    system.setDark(true)
    expect(attributeTheme()).toBe('light')
  })

  it('can be initialised again after being disposed', () => {
    const system = stubSystemScheme(false)
    const store = useThemeStore()
    store.init()
    store.dispose()
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark')

    store.init()

    expect(store.mode).toBe('dark')
    expect(attributeTheme()).toBe('dark')
    expect(system.listenerCount()).toBe(1)
    system.setDark(true)
    store.setMode('system')
    expect(attributeTheme()).toBe('dark')
  })

  it('stops updating the document once disposed', () => {
    stubSystemScheme(false)
    const store = useThemeStore()
    store.init()

    store.dispose()
    store.setMode('dark')

    expect(attributeTheme()).toBe('light')
  })

  it('reflects a patched mode in the document', () => {
    stubSystemScheme(false)
    const store = useThemeStore()
    store.init()

    store.$patch({ mode: 'dark' })

    expect(attributeTheme()).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')
  })

  it('reflects a function patch in the document', () => {
    stubSystemScheme(false)
    const store = useThemeStore()
    store.init()

    store.$patch((state) => {
      state.mode = 'dark'
    })

    expect(attributeTheme()).toBe('dark')
  })

  it('follows a theme change made in another tab', () => {
    stubSystemScheme(false)
    const store = useThemeStore()
    store.init()

    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    window.dispatchEvent(new StorageEvent('storage', { key: THEME_STORAGE_KEY }))

    expect(store.mode).toBe('dark')
    expect(attributeTheme()).toBe('dark')
  })

  it('returns to system when another tab clears storage', () => {
    stubSystemScheme(true)
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light')
    const store = useThemeStore()
    store.init()

    window.localStorage.clear()
    window.dispatchEvent(new StorageEvent('storage', { key: null }))

    expect(store.mode).toBe('system')
    expect(attributeTheme()).toBe('dark')
  })

  it('ignores storage events for other keys', () => {
    stubSystemScheme(false)
    const store = useThemeStore()
    store.init()
    store.setMode('light')
    window.localStorage.setItem('other', 'dark')

    window.dispatchEvent(new StorageEvent('storage', { key: 'other' }))

    expect(store.mode).toBe('light')
  })

  it('stops listening to storage events when disposed', () => {
    stubSystemScheme(false)
    const store = useThemeStore()
    store.init()
    store.dispose()

    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    window.dispatchEvent(new StorageEvent('storage', { key: THEME_STORAGE_KEY }))

    expect(store.mode).toBe('system')
  })

  it('shares one state between consumers of the same pinia', () => {
    stubSystemScheme(false)
    const first = useThemeStore()
    const second = useThemeStore()
    first.init()

    first.setMode('dark')

    expect(second.mode).toBe('dark')
  })
})
