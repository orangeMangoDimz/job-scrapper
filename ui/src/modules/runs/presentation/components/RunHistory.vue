<script setup lang="ts">
import type { RunRecord } from '@/modules/runs/domain/entities/Run'
import { Badge } from '@/shared/components/ui/badge'

defineProps<{ runs: RunRecord[] }>()
const emit = defineEmits<{ select: [id: string] }>()
</script>

<template>
  <section aria-labelledby="run-history-heading">
    <h2 id="run-history-heading" class="text-subheading">History</h2>
    <p v-if="runs.length === 0" class="mt-2 text-body-sm text-ink-muted">No runs yet</p>
    <ul class="mt-2 flex flex-col divide-y divide-line">
      <li v-for="run in runs" :key="run.id">
        <button
          type="button"
          class="flex w-full items-center gap-3 py-2 text-left"
          @click="emit('select', run.id)"
        >
          <Badge>{{ run.status }}</Badge>
          <span class="text-body-sm">{{ run.keywords.join(', ') }}</span>
          <span class="ml-auto text-caption text-ink-muted">
            {{ run.jobCount }} jobs, {{ new Date(run.startedAt).toLocaleString() }}
          </span>
        </button>
      </li>
    </ul>
  </section>
</template>
