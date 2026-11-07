<script setup lang="ts">
import type { PrimitiveProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { Primitive } from 'reka-ui'
import { cn } from '@/shared/utils/cn'

const props = withDefaults(
  defineProps<
    PrimitiveProps & {
      size?: 'sm' | 'md'
      isActive?: boolean
      class?: HTMLAttributes['class']
    }
  >(),
  {
    as: 'a',
    size: 'md',
  },
)
</script>

<template>
  <Primitive
    data-slot="sidebar-menu-sub-button"
    data-sidebar="menu-sub-button"
    :as="as"
    :as-child="asChild"
    :data-size="size"
    :data-active="isActive || undefined"
    :class="
      cn(
        'flex h-8 min-w-0 items-center gap-2 overflow-hidden rounded-md px-2 text-ink-muted outline-none hover:bg-surface hover:text-ink focus-visible:focus-ring data-active:bg-accent-soft data-active:font-semibold data-active:text-accent data-active:hover:bg-accent-soft data-active:hover:text-accent data-[size=md]:text-body-sm data-[size=sm]:text-caption group-data-[collapsible=icon]:hidden disabled:pointer-events-none disabled:opacity-50 aria-disabled:cursor-default [&>span:last-child]:truncate [&>svg]:size-4 [&>svg]:shrink-0',
        props.class,
      )
    "
  >
    <slot />
  </Primitive>
</template>
