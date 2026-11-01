<script setup lang="ts">
import type { LabelProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { Label } from 'reka-ui'
import { cn } from '@/shared/utils/cn'

const props = defineProps<LabelProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <Label
    data-slot="label"
    v-bind="delegatedProps"
    :class="
      cn(
        'flex items-center gap-2 text-body-sm font-semibold text-ink select-none peer-disabled:cursor-not-allowed group-data-[disabled=true]:pointer-events-none',
        props.class,
      )
    "
  >
    <slot />
  </Label>
</template>
