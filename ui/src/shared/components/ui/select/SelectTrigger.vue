<script setup lang="ts">
import type { SelectTriggerProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { ChevronDownIcon } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import { SelectIcon, SelectTrigger, useForwardProps } from 'reka-ui'
import { cn } from '@/shared/utils/cn'

const props = defineProps<SelectTriggerProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <SelectTrigger
    data-slot="select-trigger"
    v-bind="forwarded"
    :class="
      cn(
        'flex h-10 w-full min-w-0 cursor-pointer items-center justify-between gap-2 rounded-md border border-line-strong bg-surface px-3 text-left text-body text-ink outline-none transition-colors duration-150 focus-visible:border-accent focus-visible:focus-ring aria-invalid:border-danger disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-ink-muted data-placeholder:text-ink-muted [&>span]:truncate',
        props.class,
      )
    "
  >
    <slot />
    <SelectIcon as-child>
      <ChevronDownIcon class="size-5 shrink-0 text-ink-muted" aria-hidden="true" />
    </SelectIcon>
  </SelectTrigger>
</template>
