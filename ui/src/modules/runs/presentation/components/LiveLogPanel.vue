<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useLiveLog } from '@/modules/runs/presentation/composables/useLiveLog'
import PageSection from '@/shared/components/PageSection.vue'
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
  <PageSection title="Live logs" description="Output from the scraper as it runs">
    <template #actions>
      <Badge :tone="isConnected ? 'accent' : 'neutral'">
        <span
          aria-hidden="true"
          :class="['size-2 rounded-full', isConnected ? 'bg-accent' : 'bg-line-strong']"
        />
        {{ isConnected ? 'Connected' : 'Disconnected' }}
      </Badge>
    </template>
    <div
      ref="panel"
      role="log"
      aria-live="off"
      aria-label="Scraper output"
      tabindex="0"
      class="h-72 overflow-auto rounded-md border border-line bg-surface-subtle p-4 font-mono text-code text-ink outline-none focus-visible:focus-ring"
    >
      <p v-if="lines.length === 0" class="text-ink-muted">Waiting for output…</p>
      <p v-for="(line, index) in lines" :key="index" class="break-all whitespace-pre-wrap">
        {{ line }}
      </p>
    </div>
  </PageSection>
</template>
