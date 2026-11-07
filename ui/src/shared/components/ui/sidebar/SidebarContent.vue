<script setup lang="ts">
import type { PrimitiveProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { Primitive } from 'reka-ui'
import { cn } from '@/shared/utils/cn'

const props = defineProps<
  PrimitiveProps & {
    class?: HTMLAttributes['class']
  }
>()
</script>

<template>
  <Primitive
    data-slot="sidebar-content"
    data-sidebar="content"
    :as="as"
    :as-child="asChild"
    :class="
      cn(
        'flex min-h-0 flex-1 flex-col gap-8 overflow-auto group-data-[collapsible=icon]:overflow-hidden',
        props.class,
      )
    "
  >
    <slot />
  </Primitive>
</template>
