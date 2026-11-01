<script setup lang="ts">
import type { CheckboxRootEmits, CheckboxRootProps } from 'reka-ui'

import type { HTMLAttributes } from 'vue'
import { CheckIcon, MinusIcon } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import { CheckboxIndicator, CheckboxRoot, useForwardPropsEmits } from 'reka-ui'
import { cn } from '@/shared/utils/cn'

const props = defineProps<CheckboxRootProps & { class?: HTMLAttributes['class'] }>()
const emits = defineEmits<CheckboxRootEmits>()

const delegatedProps = reactiveOmit(props, 'class')

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <CheckboxRoot
    v-slot="slotProps"
    data-slot="checkbox"
    v-bind="forwarded"
    :class="
      cn(
        'peer relative flex size-5 shrink-0 cursor-pointer items-center justify-center rounded-sm border border-line-strong bg-surface text-on-accent transition-colors duration-150 outline-none after:absolute after:-inset-x-3 after:-inset-y-2 focus-visible:focus-ring disabled:cursor-not-allowed disabled:border-line disabled:bg-surface-subtle aria-invalid:border-danger data-checked:border-accent data-checked:bg-accent data-[state=indeterminate]:border-accent data-[state=indeterminate]:bg-accent',
        props.class,
      )
    "
  >
    <CheckboxIndicator
      data-slot="checkbox-indicator"
      class="grid place-content-center text-current [&>svg]:size-4"
    >
      <slot v-bind="slotProps">
        <MinusIcon v-if="slotProps.modelValue === 'indeterminate'" />
        <CheckIcon v-else />
      </slot>
    </CheckboxIndicator>
  </CheckboxRoot>
</template>
