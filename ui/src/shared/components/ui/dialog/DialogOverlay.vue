<script setup lang="ts">
import type { DialogOverlayProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { DialogOverlay } from 'reka-ui'
import { cn } from '@/shared/utils/cn'

const props = defineProps<DialogOverlayProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')
</script>

<template>
  <DialogOverlay
    data-slot="dialog-overlay"
    v-bind="delegatedProps"
    :class="
      cn(
        'fixed inset-0 z-50 bg-ink/45 dark:bg-surface/70 duration-150 data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0',
        props.class,
      )
    "
  >
    <slot />
  </DialogOverlay>
</template>
