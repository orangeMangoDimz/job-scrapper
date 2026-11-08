<script setup lang="ts">
import { computed } from 'vue'
import { Input } from '@/shared/components/ui/input'
import { parseKeywords } from '@/shared/utils/parseKeywords'

const props = defineProps<{
  id: string
  modelValue: string[]
  placeholder?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [items: string[]]
}>()

const text = computed({
  get: () => props.modelValue.join(', '),
  set: (next: string) => emit('update:modelValue', parseKeywords(next)),
})
</script>

<template>
  <Input :id="id" v-model="text" :placeholder="placeholder" />
</template>
