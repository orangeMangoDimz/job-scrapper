<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import LiveLogPanel from '@/modules/runs/presentation/components/LiveLogPanel.vue'
import RunForm from '@/modules/runs/presentation/components/RunForm.vue'
import RunHistory from '@/modules/runs/presentation/components/RunHistory.vue'
import RunResults from '@/modules/runs/presentation/components/RunResults.vue'
import { useRunStore } from '@/modules/runs/presentation/stores/useRunStore'
import { Skeleton } from '@/shared/components/ui/skeleton'

const store = useRunStore()

onMounted(() => void store.load())
onBeforeUnmount(() => store.stopPolling())
</script>

<template>
  <div class="flex flex-col gap-8">
    <h1 class="text-title">Runs</h1>
    <Skeleton v-if="store.status === 'loading'" class="h-40" />
    <p v-else-if="store.status === 'error'" role="alert">{{ store.errorMessage }}</p>
    <template v-else-if="store.options">
      <p v-if="store.options.isStale" class="text-body-sm text-ink-muted">
        The scraper is busy, so this list may be out of date
      </p>
      <RunForm
        :options="store.options"
        :is-running="store.isRunning"
        @start="(keywords, sites) => store.start(keywords, sites)"
      />
      <p v-if="store.actionError" role="alert" class="text-body-sm">{{ store.actionError }}</p>
    </template>
    <LiveLogPanel />
    <RunResults v-if="store.selected" :detail="store.selected" />
    <RunHistory :runs="store.runs" @select="store.select" />
  </div>
</template>
