import { onMounted, ref, type Ref } from 'vue'
import { useEventListener } from '@vueuse/core'

const READING_LINE_OFFSET = 128

export function useActiveSection(ids: readonly string[]): Ref<string> {
  const activeId = ref(ids[0] ?? '')

  function update(): void {
    if (
      window.scrollY > 0 &&
      window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 1
    ) {
      activeId.value = ids[ids.length - 1] ?? ''
      return
    }
    const passed = ids.filter(
      (id) =>
        (document.getElementById(id)?.getBoundingClientRect().top ?? Infinity) <=
        READING_LINE_OFFSET,
    )
    activeId.value = passed[passed.length - 1] ?? ids[0] ?? ''
  }

  useEventListener(window, 'scroll', update, { passive: true })
  useEventListener(window, 'resize', update, { passive: true })
  onMounted(update)

  return activeId
}
