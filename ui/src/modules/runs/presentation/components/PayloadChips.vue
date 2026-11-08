<script setup lang="ts">
import type { RunPayload } from '@/modules/runs/domain/entities/Run'
import { cn } from '@/shared/utils/cn'

defineProps<{ payloads: RunPayload[]; pickedIndex: number }>()
const emit = defineEmits<{ pick: [index: number] }>()
</script>

<template>
  <div role="group" aria-label="Site and keyword" class="flex flex-wrap gap-2">
    <button
      v-for="(payload, index) in payloads"
      :key="index"
      type="button"
      data-slot="payload-chip"
      :aria-pressed="index === pickedIndex"
      :class="
        cn(
          'inline-flex h-8 max-w-full cursor-pointer items-center rounded-full border px-3 text-body-sm font-semibold outline-none',
          'transition-colors duration-150 focus-visible:focus-ring',
          index === pickedIndex
            ? 'border-transparent bg-accent text-on-accent hover:bg-accent-hover'
            : 'border-line-strong bg-surface text-ink hover:border-accent hover:bg-accent-soft hover:text-accent',
        )
      "
      @click="emit('pick', index)"
    >
      <span class="truncate">{{ payload.site }} · {{ payload.keyword }}</span>
    </button>
  </div>
</template>
