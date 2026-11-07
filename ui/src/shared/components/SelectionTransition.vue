<script setup lang="ts">
/**
 * Fades and slides in the content when its key changes, such as the detail pane
 * of the selected card. The old content leaves at once, so refs to it never go
 * stale and the layout never holds two panes.
 */
</script>

<template>
  <Transition
    enter-active-class="transition-[opacity,transform] duration-200 ease-out"
    enter-from-class="translate-y-2 opacity-0"
  >
    <slot />
  </Transition>
</template>
