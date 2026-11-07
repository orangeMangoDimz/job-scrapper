<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { computed, ref, useId } from 'vue'
import { Button } from '@/shared/components/ui/button'
import { Input as BaseInput } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { cn } from '@/shared/utils/cn'

defineOptions({
  inheritAttrs: false,
})

const props = defineProps<{
  label: string
  modelValue: string
  id?: string
  error?: string
  hint?: string
  placeholder?: string
  isInvalid?: boolean
  describedBy?: string
  class?: HTMLAttributes['class']
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const generatedId = useId()
const isVisible = ref(false)

const inputId = computed(() => props.id ?? generatedId)
const messageId = computed(() => `${inputId.value}-msg`)
const message = computed(() => props.error || props.hint)
const resolvedPlaceholder = computed(() => props.placeholder ?? props.label)
const describedByIds = computed(
  () =>
    [message.value ? messageId.value : '', props.describedBy ?? ''].filter(Boolean).join(' ') ||
    undefined,
)

function toggleVisibility(): void {
  isVisible.value = !isVisible.value
}
</script>

<template>
  <div :class="cn('flex flex-col gap-2', props.class)">
    <div class="flex flex-wrap items-center justify-between gap-x-3">
      <Label :for="inputId">{{ label }}</Label>
      <slot name="labelAction" />
    </div>
    <div class="relative">
      <BaseInput
        v-bind="$attrs"
        :id="inputId"
        :placeholder="resolvedPlaceholder"
        class="pr-20"
        spellcheck="false"
        autocapitalize="off"
        autocorrect="off"
        :type="isVisible ? 'text' : 'password'"
        :model-value="modelValue"
        :aria-invalid="error || isInvalid ? 'true' : undefined"
        :aria-describedby="describedByIds"
        @update:model-value="emit('update:modelValue', String($event))"
      />
      <Button
        variant="ghost"
        size="sm"
        class="absolute top-1 right-1"
        :aria-controls="inputId"
        @click="toggleVisibility"
      >
        {{ isVisible ? 'Hide' : 'Show' }}<span class="sr-only"> password</span>
      </Button>
    </div>
    <p
      v-if="message"
      :id="messageId"
      :class="cn('text-body-sm text-ink-muted', error && 'text-danger')"
    >
      {{ message }}
    </p>
  </div>
</template>
