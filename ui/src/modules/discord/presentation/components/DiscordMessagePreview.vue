<script setup lang="ts">
defineProps<{ messages: string[] }>()
</script>

<template>
  <ol class="flex flex-col gap-3">
    <li
      v-for="(message, index) in messages"
      :key="index"
      data-slot="discord-preview-message"
      class="rounded-md border border-line bg-surface-subtle p-4 font-mono text-code break-words whitespace-pre-wrap text-ink"
    >
      {{ message }}
    </li>
  </ol>
</template>
