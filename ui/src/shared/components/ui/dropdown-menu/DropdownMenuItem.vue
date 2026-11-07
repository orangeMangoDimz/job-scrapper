<script setup lang="ts">
import type { DropdownMenuItemEmits, DropdownMenuItemProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { DropdownMenuItem, useForwardPropsEmits } from 'reka-ui'
import { cn } from '@/shared/utils/cn'

const VARIANT_CLASSES = {
  default: 'text-ink-muted data-highlighted:bg-surface-subtle data-highlighted:text-ink',
  danger: 'text-danger data-highlighted:bg-danger-soft',
} as const

const props = withDefaults(
  defineProps<
    DropdownMenuItemProps & {
      class?: HTMLAttributes['class']
      variant?: keyof typeof VARIANT_CLASSES
    }
  >(),
  {
    variant: 'default',
  },
)

const emits = defineEmits<DropdownMenuItemEmits>()

const delegatedProps = reactiveOmit(props, 'class', 'variant')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <DropdownMenuItem
    data-slot="dropdown-menu-item"
    :data-variant="variant"
    v-bind="forwarded"
    :class="
      cn(
        'flex h-11 cursor-pointer items-center gap-3 rounded-md px-3 text-body font-medium outline-none select-none focus-visible:focus-ring data-disabled:cursor-default [&_svg]:size-5 [&_svg]:shrink-0',
        VARIANT_CLASSES[variant],
        props.class,
      )
    "
  >
    <slot />
  </DropdownMenuItem>
</template>
