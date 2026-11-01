<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useLiveLog } from '@/modules/runs/presentation/composables/useLiveLog'
import { Badge } from '@/shared/components/ui/badge'

const { lines, isConnected } = useLiveLog()
const panel = ref<HTMLElement | null>(null)

watch(lines, async () => {
  await nextTick()
  if (panel.value !== null) {
    panel.value.scrollTop = panel.value.scrollHeight
  }
})
</script>

<template>
  <section aria-labelledby="live-log-heading">
    <div class="flex items-center gap-2">
      <h2 id="live-log-heading" class="text-subheading">Live logs</h2>
      <Badge>{{ isConnected ? 'Connected' : 'Disconnected' }}</Badge>
    </div>
    <div
      ref="panel"
      role="log"
      aria-live="off"
      class="mt-2 h-64 overflow-auto rounded-lg border border-line bg-surface-subtle p-3 font-mono text-code"
    >
      <p v-for="(line, index) in lines" :key="index" class="break-all whitespace-pre-wrap">
        {{ line }}
      </p>
    </div>
  </section>
</template>
