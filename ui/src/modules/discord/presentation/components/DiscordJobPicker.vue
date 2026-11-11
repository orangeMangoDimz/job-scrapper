<script setup lang="ts">
import { computed } from 'vue'
import { MAX_JOBS_PER_SEND } from '@/modules/discord/domain/entities/Discord'
import type { RunDetail, RunRecord } from '@/modules/runs/domain/entities/Run'
import { formatJobCount } from '@/modules/runs/presentation/components/runStatus'
import EmptyState from '@/shared/components/EmptyState.vue'
import { Button } from '@/shared/components/ui/button'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { Label } from '@/shared/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'

const props = defineProps<{
  runs: RunRecord[]
  detail: RunDetail | null
  pickedIndexes: number[]
  isLoading: boolean
  error: string | null
}>()

const emit = defineEmits<{
  selectRun: [id: string]
  pick: [index: number, isPicked: boolean]
  pickAll: []
  clear: []
}>()

const pickedCount = computed(() => props.pickedIndexes.length)
const isOverLimit = computed(() => pickedCount.value > MAX_JOBS_PER_SEND)
const hasPicks = computed(() => pickedCount.value > 0)

function formatStartedAt(value: string): string {
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function toRunLabel(run: RunRecord): string {
  return `${run.keywords.join(', ')} · ${formatJobCount(run.jobCount)} · ${formatStartedAt(run.startedAt)}`
}

function toJobMeta(parts: (string | null)[]): string {
  return parts.filter((part): part is string => Boolean(part)).join(' · ')
}

function setPicked(index: number, isPicked: boolean | 'indeterminate'): void {
  emit('pick', index, isPicked === true)
}
</script>

<template>
  <EmptyState
    v-if="runs.length === 0"
    compact
    title="No runs with jobs yet."
    hint="Run a scrape first, then send its jobs here."
  />
  <div v-else class="flex min-w-0 flex-col gap-4">
    <div class="flex flex-col gap-2">
      <Label for="discord-run">Run</Label>
      <Select
        :model-value="detail?.record.id"
        @update:model-value="emit('selectRun', String($event))"
      >
        <SelectTrigger id="discord-run">
          <SelectValue placeholder="Pick a run" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="run in runs" :key="run.id" :value="run.id">
            {{ toRunLabel(run) }}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>

    <p v-if="isLoading" role="status" class="text-body-sm text-ink-muted">Loading jobs</p>
    <p v-else-if="error" role="alert" class="text-body-sm text-danger">{{ error }}</p>
    <p v-else-if="detail === null" class="text-body-sm text-ink-muted">
      Pick a run to see its jobs
    </p>
    <template v-else>
      <div class="flex flex-wrap items-center justify-between gap-3">
        <p class="text-body-sm text-ink-muted">
          {{ pickedCount }} of {{ detail.jobs.length }} jobs picked
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          data-slot="toggle-all"
          @click="hasPicks ? emit('clear') : emit('pickAll')"
        >
          {{ hasPicks ? 'Clear all' : 'Pick all' }}
        </Button>
      </div>
      <p v-if="isOverLimit" role="alert" class="text-body-sm text-danger">
        Discord takes at most {{ MAX_JOBS_PER_SEND }} jobs per send, and {{ pickedCount }} are
        picked. Untick some to send
      </p>
      <ul class="flex flex-col gap-3">
        <li
          v-for="(job, index) in detail.jobs"
          :key="index"
          data-slot="discord-job"
          class="flex items-start gap-3 rounded-md border border-line p-4"
        >
          <Checkbox
            :id="`discord-job-${index}`"
            class="mt-0.5"
            :model-value="pickedIndexes.includes(index)"
            @update:model-value="setPicked(index, $event)"
          />
          <Label :for="`discord-job-${index}`" class="min-w-0 flex-col items-start gap-0">
            <span class="max-w-full truncate text-body font-semibold text-ink">
              {{ job.title ?? 'Untitled job' }}
            </span>
            <span class="max-w-full truncate text-body-sm font-normal text-ink-muted">
              {{ toJobMeta([job.company, job.location]) }}
            </span>
          </Label>
        </li>
      </ul>
    </template>
  </div>
</template>
