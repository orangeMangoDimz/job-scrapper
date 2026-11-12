<script setup lang="ts">
import { useId } from 'vue'
import type { RunRecord } from '@/modules/runs/domain/entities/Run'
import DiscordStatusText from '@/modules/runs/presentation/components/DiscordStatusText.vue'
import { formatJobCount, RUN_STATUS_VIEWS } from '@/modules/runs/presentation/components/runStatus'
import EmptyState from '@/shared/components/EmptyState.vue'
import ShowMoreToggle from '@/shared/components/ShowMoreToggle.vue'
import { Badge, BADGE_ON_ACCENT_SOFT_CLASS } from '@/shared/components/ui/badge'
import { useCollapsibleList } from '@/shared/composables/useCollapsibleList'

const props = defineProps<{ runs: RunRecord[]; selectedId: string | null }>()
const emit = defineEmits<{ select: [id: string] }>()

const listId = useId()
const {
  isExpanded,
  hiddenCount,
  visibleItems: visibleRuns,
  toggle,
} = useCollapsibleList(
  () => props.runs,
  (run) => run.id === props.selectedId,
)

const ROW_CLASS = [
  'flex w-full cursor-pointer flex-col gap-1 rounded-md border border-line p-4 text-left outline-none transition-[border-color,background-color,box-shadow] duration-200 ease-out hover:bg-surface-subtle focus-visible:focus-ring aria-[current=true]:border-accent aria-[current=true]:bg-accent-soft',
  BADGE_ON_ACCENT_SOFT_CLASS,
]

function formatStartedAt(value: string): string {
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}
</script>

<template>
  <EmptyState
    v-if="runs.length === 0"
    compact
    title="No runs yet."
    hint="Start a scrape above to see it here."
  />
  <div v-else class="flex flex-col gap-4 md:gap-3">
    <ul :id="listId" class="flex flex-col gap-4 md:gap-3">
      <li v-for="run in visibleRuns" :key="run.id">
        <button
          type="button"
          :class="ROW_CLASS"
          :aria-current="run.id === selectedId ? 'true' : undefined"
          @click="emit('select', run.id)"
        >
          <span class="flex w-full items-center gap-2">
            <span class="min-w-0 flex-1 truncate text-body font-semibold text-ink">
              {{ run.keywords.join(', ') }}
            </span>
            <Badge :tone="RUN_STATUS_VIEWS[run.status].tone">
              {{ RUN_STATUS_VIEWS[run.status].label }}
            </Badge>
          </span>
          <span class="text-body-sm text-ink-muted">
            {{ run.sites.join(', ') }} · {{ formatJobCount(run.jobCount) }}
          </span>
          <DiscordStatusText :record="run" class="text-caption" />
          <span class="text-caption text-ink-muted">{{ formatStartedAt(run.startedAt) }}</span>
        </button>
      </li>
    </ul>
    <ShowMoreToggle
      v-if="hiddenCount > 0"
      :controls="listId"
      :is-expanded="isExpanded"
      :hidden-count="hiddenCount"
      @toggle="toggle"
    />
  </div>
</template>
