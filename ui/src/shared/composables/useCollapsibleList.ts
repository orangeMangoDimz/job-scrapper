import { computed, ref, toValue, type ComputedRef, type MaybeRefOrGetter, type Ref } from 'vue'

const COLLAPSED_COUNT = 3

export interface CollapsibleList<T> {
  isExpanded: Ref<boolean>
  hiddenCount: ComputedRef<number>
  visibleItems: ComputedRef<readonly T[]>
  toggle: () => void
}

export function useCollapsibleList<T>(
  items: MaybeRefOrGetter<readonly T[]>,
  isPinned: (item: T) => boolean = () => false,
): CollapsibleList<T> {
  const isExpanded = ref(false)
  const collapsedItems = computed(() =>
    toValue(items).filter((item, index) => index < COLLAPSED_COUNT || isPinned(item)),
  )
  const hiddenCount = computed(() => toValue(items).length - collapsedItems.value.length)
  const visibleItems = computed(() => (isExpanded.value ? toValue(items) : collapsedItems.value))

  function toggle(): void {
    isExpanded.value = !isExpanded.value
  }

  return { isExpanded, hiddenCount, visibleItems, toggle }
}
