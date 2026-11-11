<script setup lang="ts">
import type { SelectItemProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { CheckIcon } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import { SelectItem, SelectItemIndicator, SelectItemText, useForwardProps } from 'reka-ui'
import { cn } from '@/shared/utils/cn'

const props = defineProps<SelectItemProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <SelectItem
    data-slot="select-item"
    v-bind="forwarded"
    :class="
      cn(
        'flex min-h-10 cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-body font-medium text-ink-muted outline-none select-none data-highlighted:bg-surface-subtle data-highlighted:text-ink data-[state=checked]:text-ink data-disabled:cursor-default data-disabled:opacity-50 [&_svg]:size-5 [&_svg]:shrink-0',
        props.class,
      )
    "
  >
    <SelectItemText class="min-w-0 flex-1 truncate">
      <slot />
    </SelectItemText>
    <SelectItemIndicator class="ml-auto text-accent">
      <CheckIcon aria-hidden="true" />
    </SelectItemIndicator>
  </SelectItem>
</template>
