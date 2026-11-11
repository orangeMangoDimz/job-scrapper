<script setup lang="ts">
import { useId } from 'vue'

defineProps<{
  title: string
  description?: string
}>()

const headingId = useId()
</script>

<template>
  <section
    :aria-labelledby="headingId"
    class="flex flex-col gap-3 rounded-lg border border-line p-4 sm:p-6"
  >
    <div class="flex items-center justify-between gap-3">
      <div class="flex min-w-0 flex-col">
        <h3 :id="headingId" class="text-heading text-ink">{{ title }}</h3>
        <p v-if="description" class="text-body-sm text-ink-muted">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="flex shrink-0 items-center gap-2">
        <slot name="actions" />
      </div>
    </div>
    <slot />
  </section>
</template>
