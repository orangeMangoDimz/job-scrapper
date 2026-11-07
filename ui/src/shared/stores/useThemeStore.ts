import { computed, ref, watch, type WatchHandle } from 'vue'
import { defineStore } from 'pinia'
import {
  DEFAULT_THEME_MODE,
  resolveTheme,
  THEME_STORAGE_KEY,
  type ResolvedTheme,
  type ThemeMode,
} from '@/shared/utils/theme'
import { readThemeMode, writeThemeMode } from '@/shared/utils/themeStorage'

const DARK_SCHEME_QUERY = '(prefers-color-scheme: dark)'

function applyTheme(theme: ResolvedTheme): void {
  const root = document.documentElement
  root.dataset.theme = theme
  root.style.colorScheme = theme
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>(DEFAULT_THEME_MODE)
  const isSystemDark = ref(false)
  const resolvedTheme = computed<ResolvedTheme>(() => resolveTheme(mode.value, isSystemDark.value))
  let stopWatching: WatchHandle | null = null
  let stopListening: (() => void) | null = null

  function listenToSystem(): () => void {
    const query = window.matchMedia(DARK_SCHEME_QUERY)
    isSystemDark.value = query.matches
    const onChange = (event: MediaQueryListEvent): void => {
      isSystemDark.value = event.matches
    }
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }

  function listenToStorage(): () => void {
    const onStorage = (event: StorageEvent): void => {
      if (event.key === null || event.key === THEME_STORAGE_KEY) {
        mode.value = readThemeMode()
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }

  function init(): void {
    if (stopListening) {
      return
    }
    mode.value = readThemeMode()
    const stopSystem = listenToSystem()
    const stopStorage = listenToStorage()
    stopListening = () => {
      stopSystem()
      stopStorage()
    }
    stopWatching = watch(resolvedTheme, applyTheme, { immediate: true, flush: 'sync' })
  }

  function dispose(): void {
    stopWatching?.stop()
    stopWatching = null
    stopListening?.()
    stopListening = null
  }

  function setMode(next: ThemeMode): void {
    mode.value = next
    writeThemeMode(next)
  }

  return { mode, resolvedTheme, init, dispose, setMode }
})
