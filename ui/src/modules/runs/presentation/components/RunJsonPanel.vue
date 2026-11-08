<script setup lang="ts">
import { computed } from 'vue'
import type { JsonObject, RunPayload } from '@/modules/runs/domain/entities/Run'
import JsonViewer from '@/modules/runs/presentation/components/JsonViewer.vue'
import PayloadChips from '@/modules/runs/presentation/components/PayloadChips.vue'
import type { JsonTab } from '@/modules/runs/presentation/components/resultsTabStorage'

const props = defineProps<{
  payloads: RunPayload[]
  pickedIndex: number
  field: JsonTab
}>()
const emit = defineEmits<{ pick: [index: number] }>()

const MISSING_NOTES = {
  raw: 'Raw data was not saved for this run',
  filtered: 'Filtered data was not saved for this run',
} as const

const shown = computed(() => props.payloads[props.pickedIndex]?.[props.field] ?? null)

// Jobs files carry a count or a jobs list, other files show no count
function toJobCount({ count, jobs }: JsonObject): number | null {
  if (typeof count === 'number' && Number.isFinite(count)) {
    return count
  }
  return Array.isArray(jobs) ? jobs.length : null
}

const jobCount = computed(() => (shown.value === null ? null : toJobCount(shown.value)))
</script>

<template>
  <PayloadChips
    v-if="payloads.length > 0"
    :payloads="payloads"
    :picked-index="pickedIndex"
    @pick="emit('pick', $event)"
  />
  <JsonViewer v-if="shown !== null" :value="shown" :job-count="jobCount" />
  <p
    v-else
    data-slot="json-missing"
    class="rounded-lg border border-dashed border-line-strong p-6 text-center text-body-sm text-ink-muted"
  >
    {{ MISSING_NOTES[field] }}
  </p>
</template>
