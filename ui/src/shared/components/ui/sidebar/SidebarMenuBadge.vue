<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/shared/utils/cn'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <span
    data-slot="sidebar-menu-badge"
    data-sidebar="menu-badge"
    :class="
      cn(
        'ml-auto flex h-6 min-w-6 shrink-0 items-center justify-center rounded-full bg-accent px-2 text-caption font-bold text-on-accent tabular-nums select-none sidebar-fade',
        props.class,
      )
    "
  >
    <slot />
  </span>
</template>
