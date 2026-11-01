<script setup lang="ts">
defineProps<{
  id: string
  modelValue: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [items: string[]]
}>()

function update(event: Event): void {
  const text = (event.target as HTMLTextAreaElement).value
  const items = text
    .split('\n')
    .map((item) => item.trim())
    .filter((item) => item !== '')
  emit('update:modelValue', items)
}
</script>

<template>
  <textarea
    :id="id"
    :value="modelValue.join('\n')"
    rows="3"
    class="w-full min-w-0 rounded-md border border-line-strong bg-surface px-3 py-2 text-body text-ink outline-none transition-colors duration-150 focus-visible:border-accent focus-visible:focus-ring disabled:cursor-not-allowed disabled:bg-surface-subtle disabled:text-ink-muted"
    @change="update"
  />
</template>
