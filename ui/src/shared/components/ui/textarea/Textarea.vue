<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { useVModel } from '@vueuse/core'
import { cn } from '@/shared/utils/cn'

const props = defineProps<{
  defaultValue?: string
  modelValue?: string
  class?: HTMLAttributes['class']
}>()

const emits = defineEmits<{
  (e: 'update:modelValue', payload: string): void
}>()

const modelValue = useVModel(props, 'modelValue', emits, {
  passive: true,
  defaultValue: props.defaultValue,
})
</script>

<template>
  <textarea
    v-model="modelValue"
    data-slot="textarea"
    :class="
      cn(
        'min-h-24 w-full min-w-0 resize-y rounded-md border border-line-strong bg-surface px-3 py-2 text-body text-ink outline-none transition-colors duration-150 placeholder:text-ink-muted focus-visible:border-accent focus-visible:focus-ring aria-invalid:border-danger disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-ink-muted',
        props.class,
      )
    "
  />
</template>
