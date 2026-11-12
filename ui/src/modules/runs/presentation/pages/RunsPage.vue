<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { toast } from 'vue-sonner'
import RunConfigSection from '@/modules/config/presentation/components/RunConfigSection.vue'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import { useDiscordSettingsStore } from '@/modules/discord/presentation/stores/useDiscordSettingsStore'
import LiveLogPanel from '@/modules/runs/presentation/components/LiveLogPanel.vue'
import RunForm from '@/modules/runs/presentation/components/RunForm.vue'
import RunHistory from '@/modules/runs/presentation/components/RunHistory.vue'
import RunResults from '@/modules/runs/presentation/components/RunResults.vue'
import { toNotifyDiscordBlock } from '@/modules/runs/presentation/components/notifyDiscordBlock'
import { toDiscordStatusView } from '@/modules/runs/presentation/components/runStatus'
import { useRunStore } from '@/modules/runs/presentation/stores/useRunStore'
import PageSection from '@/shared/components/PageSection.vue'
import { Button } from '@/shared/components/ui/button'
import { Skeleton } from '@/shared/components/ui/skeleton'

const store = useRunStore()
const configStore = useConfigStore()
const discordSettingsStore = useDiscordSettingsStore()
const isPending = computed(() => store.status === 'idle' || store.status === 'loading')
const isFirstLoad = computed(() => isPending.value && store.options === null)
const showsHistory = computed(() => store.options !== null || isFirstLoad.value)
const selectedId = computed(() => store.selected?.record.id ?? null)
const notifyDiscordBlock = computed(() =>
  toNotifyDiscordBlock(discordSettingsStore.status, discordSettingsStore.settings),
)

watch(
  () => store.discordOutcome,
  (record) => {
    const view = record === null ? null : toDiscordStatusView(record)
    if (view !== null) {
      toast[view.toastKind](view.label)
    }
  },
)

onMounted(() => {
  void store.load()
  if (discordSettingsStore.status === 'idle') {
    void discordSettingsStore.load()
  }
})
onBeforeUnmount(() => store.stopPolling())
</script>

<template>
  <header class="flex flex-wrap items-start justify-between gap-3">
    <h2 id="runs-heading" class="min-w-0 text-title text-ink">Runs</h2>
  </header>

  <div class="flex min-w-0 flex-col gap-6 md:gap-4">
    <p
      v-if="store.options?.isStale"
      role="status"
      class="rounded-md border border-line-strong p-4 text-body-sm text-ink"
    >
      The scraper is busy, so this list may be out of date
    </p>

    <PageSection title="Start a run">
      <div
        v-if="store.status === 'error'"
        role="alert"
        class="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line-strong p-4"
      >
        <div class="flex min-w-0 flex-col">
          <p class="text-body font-semibold text-ink">Could not load runs</p>
          <p v-if="store.errorMessage" class="text-body-sm text-ink-muted">
            {{ store.errorMessage }}
          </p>
        </div>
        <Button size="sm" @click="store.load">Try again</Button>
      </div>
      <div v-if="isFirstLoad" role="status" aria-busy="true" class="flex flex-col gap-4">
        <span class="sr-only">Loading run options</span>
        <Skeleton class="h-10 w-full" />
        <Skeleton class="h-6 w-2/3" />
        <Skeleton class="h-10 w-32" />
      </div>
      <RunForm
        v-else-if="store.options"
        :options="store.options"
        :is-running="store.isRunning"
        :discord-block="notifyDiscordBlock"
        :has-unsaved-config="configStore.isDirty"
        @start="(keywords, sites, notifyDiscord) => store.start(keywords, sites, notifyDiscord)"
      />
      <p v-if="store.actionError" role="alert" class="text-body-sm text-danger">
        {{ store.actionError }}
      </p>
    </PageSection>

    <RunConfigSection id="config" class="scroll-mt-24" />

    <RunResults v-if="store.selected" :detail="store.selected" />

    <PageSection v-if="showsHistory" title="History">
      <div v-if="isFirstLoad" role="status" aria-busy="true" class="flex flex-col gap-4 md:gap-3">
        <span class="sr-only">Loading run history</span>
        <Skeleton v-for="index in 3" :key="index" class="h-24 w-full rounded-md" />
      </div>
      <RunHistory v-else :runs="store.runs" :selected-id="selectedId" @select="store.select" />
    </PageSection>

    <LiveLogPanel />
  </div>
</template>
