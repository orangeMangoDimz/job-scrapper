import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryStorage } from '@/__tests__/memoryStorage'
import { THEME_STORAGE_KEY } from '@/shared/utils/theme'

const INDEX_HTML = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8')
const BOOT_SCRIPT = readFileSync(resolve(process.cwd(), 'public/theme-boot.js'), 'utf8')

function stubSystemDark(isDark: boolean): void {
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: isDark, media: query }))
}

function runBootScript(): void {
  new Function(BOOT_SCRIPT)()
}

function resetRoot(): void {
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.style.colorScheme = ''
}

describe('theme boot script', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createMemoryStorage())
    resetRoot()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    resetRoot()
  })

  it('loads from the head before the app, without being a module', () => {
    const head = /<head>([\s\S]*?)<\/head>/.exec(INDEX_HTML)?.[1] ?? ''

    expect(head).toContain('<script src="/theme-boot.js"></script>')
  })

  it('reads exactly the storage key the app writes', () => {
    stubSystemDark(false)
    const getItem = vi.spyOn(window.localStorage, 'getItem')

    runBootScript()

    expect(getItem).toHaveBeenCalledTimes(1)
    expect(getItem).toHaveBeenCalledWith(THEME_STORAGE_KEY)
  })

  it('applies a stored dark mode before the app loads', () => {
    stubSystemDark(false)
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark')

    runBootScript()

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')
  })

  it('applies a stored light mode even when the system is dark', () => {
    stubSystemDark(true)
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light')

    runBootScript()

    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('follows the system when nothing valid is stored', () => {
    stubSystemDark(true)
    window.localStorage.setItem(THEME_STORAGE_KEY, 'sepia')

    runBootScript()

    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('still follows the system when storage is blocked', () => {
    stubSystemDark(true)
    vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })

    runBootScript()

    expect(document.documentElement.dataset.theme).toBe('dark')
  })
})
