<script setup lang="ts">
import type { DropdownMenuRadioItemEmits, DropdownMenuRadioItemProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { CheckIcon } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import { DropdownMenuItemIndicator, DropdownMenuRadioItem, useForwardPropsEmits } from 'reka-ui'
import { cn } from '@/shared/utils/cn'

const props = defineProps<DropdownMenuRadioItemProps & { class?: HTMLAttributes['class'] }>()
const emits = defineEmits<DropdownMenuRadioItemEmits>()

const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <DropdownMenuRadioItem
    data-slot="dropdown-menu-radio-item"
    v-bind="forwarded"
    :class="
      cn(
        'flex h-11 cursor-pointer items-center gap-3 rounded-md px-3 text-body font-medium text-ink-muted outline-none select-none data-highlighted:bg-surface-subtle data-highlighted:text-ink focus-visible:focus-ring data-disabled:cursor-default data-disabled:opacity-50 data-[state=checked]:text-ink [&_svg]:size-5 [&_svg]:shrink-0',
        props.class,
      )
    "
  >
    <span class="flex flex-1 items-center gap-3"><slot /></span>
    <DropdownMenuItemIndicator>
      <CheckIcon aria-hidden="true" />
    </DropdownMenuItemIndicator>
  </DropdownMenuRadioItem>
</template>
