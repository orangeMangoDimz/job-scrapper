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
    data-slot="sidebar-group-action"
    data-sidebar="group-action"
    :as="as"
    :as-child="asChild"
    :class="
      cn(
        'absolute top-3 right-3 flex size-6 items-center justify-center rounded-md p-0 text-ink outline-none transition-transform hover:bg-surface focus-visible:focus-ring group-data-[collapsible=icon]:hidden after:absolute after:-inset-2 md:after:hidden [&>svg]:size-4 [&>svg]:shrink-0',
        props.class,
      )
    "
  >
    <slot />
  </Primitive>
</template>
