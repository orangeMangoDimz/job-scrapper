<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/shared/utils/cn'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <main
    data-slot="sidebar-inset"
    :class="cn('relative flex w-full min-w-0 flex-1 flex-col bg-surface text-ink', props.class)"
  >
    <slot />
  </main>
</template>
