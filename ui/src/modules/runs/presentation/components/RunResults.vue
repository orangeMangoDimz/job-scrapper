<script setup lang="ts">
import type { RunDetail } from '@/modules/runs/domain/entities/Run'

defineProps<{ detail: RunDetail }>()
</script>

<template>
  <section aria-labelledby="run-results-heading">
    <h2 id="run-results-heading" class="text-subheading">
      Results: {{ detail.record.jobCount }} jobs
    </h2>
    <p v-if="detail.record.error" role="alert" class="mt-2 text-body-sm">
      {{ detail.record.error }}
    </p>
    <ul v-if="detail.failures.length > 0" class="mt-2 text-body-sm">
      <li v-for="failure in detail.failures" :key="`${failure.keyword}-${failure.site}`">
        {{ failure.site }}, {{ failure.keyword }}: {{ failure.reason }}
      </li>
    </ul>
    <ul class="mt-2 flex flex-col divide-y divide-line">
      <li v-for="(job, index) in detail.jobs" :key="index" class="py-2">
        <a
          v-if="job.url"
          :href="job.url"
          target="_blank"
          rel="noopener noreferrer"
          class="text-body-sm font-semibold"
        >
          {{ job.title }}
        </a>
        <p v-else class="text-body-sm font-semibold">{{ job.title }}</p>
        <p class="text-caption text-ink-muted">
          {{ job.site }}, {{ job.company }}, {{ job.location }}
        </p>
      </li>
    </ul>
  </section>
</template>
