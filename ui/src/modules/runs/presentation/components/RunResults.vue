<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { RunDetail } from '@/modules/runs/domain/entities/Run'
import RunJsonPanel from '@/modules/runs/presentation/components/RunJsonPanel.vue'
import {
  isResultsTab,
  JSON_TABS,
  readResultsTab,
  RESULTS_TABS,
  writeResultsTab,
  type ResultsTab,
} from '@/modules/runs/presentation/components/resultsTabStorage'
import { formatJobCount, RUN_STATUS_VIEWS } from '@/modules/runs/presentation/components/runStatus'
import EmptyState from '@/shared/components/EmptyState.vue'
import PageSection from '@/shared/components/PageSection.vue'
import { Badge } from '@/shared/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'

const props = defineProps<{ detail: RunDetail }>()

const TAB_LABELS: Record<ResultsTab, string> = {
  cards: 'Cards',
  raw: 'Raw JSON',
  filtered: 'Filtered JSON',
}

const tab = ref<ResultsTab>(readResultsTab())
const pickedIndex = ref(0)
// A pick past the end of the files (the list shrank) falls back to the first file
const effectiveIndex = computed(() =>
  pickedIndex.value < props.detail.payloads.length ? pickedIndex.value : 0,
)

watch(
  () => props.detail.record.id,
  () => {
    pickedIndex.value = 0
  },
)

function changeTab(next: string | number): void {
  if (isResultsTab(next)) {
    tab.value = next
    writeResultsTab(next)
  }
}

const status = computed(() => RUN_STATUS_VIEWS[props.detail.record.status])
const summary = computed(
  () =>
    `${formatJobCount(props.detail.record.jobCount)} from ${props.detail.record.keywords.join(', ')}`,
)

function safeJobUrl(url: string | null): string | null {
  return url !== null && /^https?:\/\//i.test(url) ? url : null
}

function jobMeta(parts: (string | null)[]): string {
  return parts.filter((part): part is string => Boolean(part)).join(' · ')
}
</script>

<template>
  <PageSection title="Results" :description="summary">
    <template #actions>
      <Badge :tone="status.tone">{{ status.label }}</Badge>
    </template>
    <p
      v-if="detail.record.error"
      role="alert"
      class="rounded-md bg-danger-soft p-4 text-body-sm text-danger"
    >
      {{ detail.record.error }}
    </p>
    <ul
      v-if="detail.failures.length > 0"
      aria-label="Failed searches"
      class="flex flex-col gap-2 rounded-md border border-line p-4 text-body-sm"
    >
      <li v-for="failure in detail.failures" :key="`${failure.keyword}-${failure.site}`">
        <span class="font-semibold text-ink">{{ failure.site }}, {{ failure.keyword }}:</span>
        <span class="text-ink-muted"> {{ failure.reason }}</span>
      </li>
    </ul>
    <Tabs :model-value="tab" @update:model-value="changeTab">
      <TabsList aria-label="Result views">
        <TabsTrigger v-for="name in RESULTS_TABS" :key="name" :value="name">
          {{ TAB_LABELS[name] }}
        </TabsTrigger>
      </TabsList>
      <TabsContent value="cards">
        <EmptyState
          v-if="detail.jobs.length === 0"
          compact
          title="No jobs found."
          hint="Try other keywords or sites."
        />
        <ul v-else class="flex flex-col gap-4 md:gap-3">
          <li
            v-for="(job, index) in detail.jobs"
            :key="index"
            class="flex flex-col rounded-md border border-line p-4"
          >
            <a
              v-if="safeJobUrl(job.url)"
              :href="safeJobUrl(job.url)!"
              target="_blank"
              rel="noopener noreferrer"
              class="w-fit text-body font-semibold text-link hover:underline focus-visible:focus-ring"
            >
              {{ job.title ?? 'Untitled job' }}
            </a>
            <p v-else class="text-body font-semibold text-ink">{{ job.title ?? 'Untitled job' }}</p>
            <p class="text-body-sm text-ink-muted">{{ jobMeta([job.company, job.location]) }}</p>
            <p class="text-caption text-ink-muted">{{ jobMeta([job.site, job.matchedKeyword]) }}</p>
          </li>
        </ul>
      </TabsContent>
      <TabsContent v-for="name in JSON_TABS" :key="name" :value="name">
        <RunJsonPanel
          :field="name"
          :payloads="detail.payloads"
          :picked-index="effectiveIndex"
          @pick="pickedIndex = $event"
        />
      </TabsContent>
    </Tabs>
  </PageSection>
</template>
