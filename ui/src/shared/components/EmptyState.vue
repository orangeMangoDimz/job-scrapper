<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    hint: string
    compact?: boolean
  }>(),
  { compact: false },
)
</script>

<template>
  <div
    data-slot="empty-state"
    :class="[
      'flex flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-line-strong p-6 text-center',
      !compact && 'min-h-85',
    ]"
  >
    <p class="text-body font-semibold text-ink">{{ title }}</p>
    <p class="text-body-sm text-ink-muted">{{ hint }}</p>
    <div v-if="$slots.action" data-slot="empty-state-action" class="mt-4">
      <slot name="action" />
    </div>
  </div>
</template>
