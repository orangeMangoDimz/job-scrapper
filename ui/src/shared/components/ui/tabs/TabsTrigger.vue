<script setup lang="ts">
import type { TabsTriggerProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { TabsTrigger, useForwardProps } from 'reka-ui'
import { cn } from '@/shared/utils/cn'

const props = defineProps<TabsTriggerProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')
const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <TabsTrigger
    data-slot="tabs-trigger"
    v-bind="forwardedProps"
    :class="
      cn(
        'relative -mb-px inline-flex h-10 shrink-0 cursor-pointer items-center justify-center rounded-t-md border-b-2 border-transparent px-4 text-body font-semibold whitespace-nowrap text-ink-muted outline-none select-none',
        'transition-colors duration-150 hover:bg-surface-subtle hover:text-ink',
        'focus-visible:focus-ring data-[state=active]:border-accent data-[state=active]:text-accent data-[state=active]:hover:bg-accent-soft',
        'disabled:cursor-not-allowed disabled:text-ink-muted/60 disabled:hover:bg-transparent',
        props.class,
      )
    "
  >
    <slot />
  </TabsTrigger>
</template>
