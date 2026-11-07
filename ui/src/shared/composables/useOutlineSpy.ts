import { nextTick, onScopeDispose, readonly, ref, watch } from 'vue'
import type { Ref } from 'vue'

const ACTIVE_BAND_MARGIN = '-45% 0px -50% 0px'
const KEY_SEPARATOR = '\n'
const PIN_MS = 1000

export interface OutlineSpy {
  activeKey: Readonly<Ref<string | null>>
  pin: (key: string) => void
}

function mapKeyedElements(keyAttribute: string): Map<string, HTMLElement> {
  const elements = new Map<string, HTMLElement>()
  for (const element of document.querySelectorAll<HTMLElement>(`[${keyAttribute}]`)) {
    const key = element.getAttribute(keyAttribute)
    if (key !== null && !elements.has(key)) {
      elements.set(key, element)
    }
  }
  return elements
}

export function useOutlineSpy(getKeys: () => readonly string[], keyAttribute: string): OutlineSpy {
  const activeKey = ref<string | null>(null)
  const visibleKeys = new Set<string>()
  let observer: IntersectionObserver | null = null
  let pinnedUntil = 0
  let isDisposed = false

  function updateActive(entries: readonly IntersectionObserverEntry[]): void {
    for (const entry of entries) {
      const key = entry.target.getAttribute(keyAttribute)
      if (key === null) {
        continue
      }
      if (entry.isIntersecting) {
        visibleKeys.add(key)
      } else {
        visibleKeys.delete(key)
      }
    }
    if (Date.now() < pinnedUntil) {
      return
    }
    const deepest = [...getKeys()].reverse().find((key) => visibleKeys.has(key))
    if (deepest !== undefined) {
      activeKey.value = deepest
    }
  }

  function pin(key: string): void {
    activeKey.value = key
    pinnedUntil = Date.now() + PIN_MS
  }

  function stop(): void {
    observer?.disconnect()
    observer = null
    visibleKeys.clear()
  }

  function observe(keys: readonly string[]): void {
    stop()
    if (activeKey.value !== null && !keys.includes(activeKey.value)) {
      activeKey.value = null
    }
    if (typeof IntersectionObserver === 'undefined') {
      return
    }
    observer = new IntersectionObserver(updateActive, { rootMargin: ACTIVE_BAND_MARGIN })
    const elements = mapKeyedElements(keyAttribute)
    for (const key of keys) {
      const element = elements.get(key)
      if (element !== undefined) {
        observer.observe(element)
      }
    }
  }

  watch(
    () => getKeys().join(KEY_SEPARATOR),
    async () => {
      await nextTick()
      if (!isDisposed) {
        observe(getKeys())
      }
    },
    { immediate: true },
  )

  onScopeDispose(() => {
    isDisposed = true
    stop()
  })

  return { activeKey: readonly(activeKey), pin }
}
