<script setup lang="ts">
import { computed, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import ConfigPage from '@/modules/config/presentation/pages/ConfigPage.vue'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import DiscordPage from '@/modules/discord/presentation/pages/DiscordPage.vue'
import { useDiscordSettingsStore } from '@/modules/discord/presentation/stores/useDiscordSettingsStore'
import RunsPage from '@/modules/runs/presentation/pages/RunsPage.vue'
import { useRunStore } from '@/modules/runs/presentation/stores/useRunStore'
import { isPendingStatus } from '@/shared/utils/loadStatus'

const route = useRoute()
const runStore = useRunStore()
const configStore = useConfigStore()
const discordSettingsStore = useDiscordSettingsStore()

const isSettled = computed(() =>
  [runStore.status, configStore.status, discordSettingsStore.status].every(
    (status) => !isPendingStatus(status),
  ),
)

const stopScrollWatch = watch(isSettled, (settled) => {
  if (!settled) {
    return
  }
  stopScrollWatch()
  if (route.hash !== '') {
    void nextTick(() => document.querySelector(route.hash)?.scrollIntoView())
  }
})
</script>

<template>
  <div class="flex min-w-0 flex-col gap-16">
    <section
      id="runs"
      aria-labelledby="runs-heading"
      data-slot="home-section"
      class="flex scroll-mt-24 flex-col gap-6"
    >
      <RunsPage />
    </section>
    <section
      id="config"
      aria-labelledby="config-heading"
      data-slot="home-section"
      class="flex scroll-mt-24 flex-col gap-6"
    >
      <ConfigPage />
    </section>
    <section
      id="discord"
      aria-labelledby="discord-heading"
      data-slot="home-section"
      class="flex scroll-mt-24 flex-col gap-6"
    >
      <DiscordPage />
    </section>
  </div>
</template>
