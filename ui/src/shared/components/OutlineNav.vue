<script setup lang="ts">
import type { OutlineItem } from '@/shared/components/types'
import { Badge, BADGE_ON_ACCENT_SOFT_CLASS } from '@/shared/components/ui/badge'
import { revealKeyedElement } from '@/shared/composables/revealKeyedElement'
import { useOutlineSpy } from '@/shared/composables/useOutlineSpy'

const ROW_CLASS = [
  'flex w-full cursor-pointer items-center gap-2 rounded-md px-3 py-1.5 text-left outline-none transition-colors duration-150 hover:bg-surface-subtle focus-visible:focus-ring aria-[current=location]:bg-accent-soft',
  BADGE_ON_ACCENT_SOFT_CLASS,
]

const props = withDefaults(
  defineProps<{
    items: readonly OutlineItem[]
    label: string
    keyAttribute: string
    scrollBlock?: ScrollLogicalPosition
  }>(),
  { scrollBlock: 'center' },
)

const emit = defineEmits<{
  select: [key: string]
}>()

const { activeKey, pin } = useOutlineSpy(
  () => props.items.flatMap((item) => [item.key, ...item.entries.map((entry) => entry.key)]),
  props.keyAttribute,
)

function reveal(key: string): void {
  pin(key)
  revealKeyedElement(props.keyAttribute, key, props.scrollBlock)
  emit('select', key)
}

function ariaCurrentFor(key: string): 'location' | undefined {
  return activeKey.value === key ? 'location' : undefined
}
</script>

<template>
  <nav :aria-label="label" class="flex min-w-0 flex-col rounded-lg border border-line bg-surface">
    <h2 class="border-b border-line px-4 py-3 text-subheading text-ink">Outline</h2>
    <ul class="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-2">
      <li v-for="item in items" :key="item.key" class="flex flex-col gap-1">
        <button
          type="button"
          :aria-current="ariaCurrentFor(item.key)"
          :class="ROW_CLASS"
          @click="reveal(item.key)"
        >
          <span
            class="min-w-0 flex-1 truncate text-body-sm font-medium"
            :class="item.badge || item.isMuted ? 'text-ink-muted' : 'text-ink'"
          >
            {{ item.label }}
          </span>
          <span v-if="item.isMuted" class="sr-only">, empty</span>
          <Badge v-if="item.badge" tone="neutral">{{ item.badge }}</Badge>
        </button>
        <ul
          v-if="item.entries.length > 0"
          class="ml-3 flex flex-col gap-1 border-l border-line pl-2"
        >
          <li v-for="entry in item.entries" :key="entry.key">
            <button
              type="button"
              :aria-current="ariaCurrentFor(entry.key)"
              :class="ROW_CLASS"
              @click="reveal(entry.key)"
            >
              <span class="flex min-w-0 flex-1 flex-col">
                <span class="truncate text-body-sm text-ink">{{ entry.label }}</span>
                <span v-if="entry.detail" class="truncate text-caption text-ink-muted">
                  {{ entry.detail }}
                </span>
              </span>
            </button>
          </li>
        </ul>
      </li>
    </ul>
  </nav>
</template>
