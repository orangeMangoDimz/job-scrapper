<script setup lang="ts">
import { Play } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import type { RunOptions } from '@/modules/runs/domain/entities/Run'
import type { NotifyDiscordBlock } from '@/modules/runs/presentation/components/notifyDiscordBlock'
import {
  readNotifyDiscord,
  writeNotifyDiscord,
} from '@/modules/runs/presentation/components/notifyDiscordStorage'
import { Button } from '@/shared/components/ui/button'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { parseKeywords } from '@/shared/utils/parseKeywords'

const DISCORD_ROUTE = { path: '/', hash: '#discord' }
const CONFIG_ROUTE = { path: '/', hash: '#config' }

interface DiscordHint {
  text: string
  linksToDiscord: boolean
}

const DISCORD_HINTS: Record<NotifyDiscordBlock, DiscordHint | null> = {
  loading: null,
  'load-failed': { text: 'Could not load Discord settings', linksToDiscord: false },
  'not-configured': { text: 'Save a bot token on the', linksToDiscord: true },
  'no-channel': { text: 'Set a default channel on the', linksToDiscord: true },
}

const props = withDefaults(
  defineProps<{
    options: RunOptions
    isRunning: boolean
    discordBlock?: NotifyDiscordBlock | null
    hasUnsavedConfig?: boolean
  }>(),
  { discordBlock: null, hasUnsavedConfig: false },
)
const emit = defineEmits<{ start: [keywords: string[], sites: string[], notifyDiscord: boolean] }>()

const keywordText = ref('')
const pickedSites = ref<string[]>([])
const shouldNotifyDiscord = ref(readNotifyDiscord())

const keywords = computed(() => parseKeywords(keywordText.value))
const canNotifyDiscord = computed(() => props.discordBlock === null)
const discordHint = computed(() =>
  props.discordBlock === null ? null : DISCORD_HINTS[props.discordBlock],
)
const notifyDiscord = computed(() => canNotifyDiscord.value && shouldNotifyDiscord.value)
const canStart = computed(
  () =>
    keywords.value.length > 0 &&
    pickedSites.value.length > 0 &&
    !props.isRunning &&
    !props.hasUnsavedConfig,
)

watch(
  () => props.options,
  (options) => {
    pickedSites.value = options.sites.filter((site) => site.isEnabled).map((site) => site.name)
  },
  { immediate: true },
)

function setNotifyDiscord(isPicked: boolean | 'indeterminate'): void {
  shouldNotifyDiscord.value = isPicked === true
  writeNotifyDiscord(shouldNotifyDiscord.value)
}

function setSite(name: string, isPicked: boolean | 'indeterminate'): void {
  pickedSites.value =
    isPicked === true
      ? [...pickedSites.value, name]
      : pickedSites.value.filter((site) => site !== name)
}
</script>

<template>
  <form
    class="flex flex-col gap-4"
    @submit.prevent="emit('start', keywords, pickedSites, notifyDiscord)"
  >
    <div class="flex flex-col gap-2">
      <Label for="run-keywords">Keywords, separated by commas</Label>
      <div class="flex flex-col gap-3 sm:flex-row">
        <Input
          id="run-keywords"
          v-model="keywordText"
          placeholder="data analyst, python"
          class="sm:flex-1"
        />
        <Button type="submit" variant="primary" :disabled="!canStart">
          <Play aria-hidden="true" />
          {{ isRunning ? 'Scrape running' : 'Run scrape' }}
        </Button>
      </div>
      <p v-if="hasUnsavedConfig" class="text-body-sm text-ink-muted">
        <RouterLink :to="CONFIG_ROUTE" class="text-link hover:underline">
          Save or discard config changes first
        </RouterLink>
      </p>
    </div>
    <div class="flex flex-col gap-1">
      <div class="flex items-center gap-3">
        <Checkbox
          id="run-notify-discord"
          :model-value="notifyDiscord"
          :disabled="!canNotifyDiscord"
          @update:model-value="setNotifyDiscord"
        />
        <Label for="run-notify-discord" class="cursor-pointer">Send to Discord when done</Label>
      </div>
      <p v-if="discordHint" data-slot="discord-hint" class="text-body-sm text-ink-muted">
        {{ discordHint.text }}
        <RouterLink
          v-if="discordHint.linksToDiscord"
          :to="DISCORD_ROUTE"
          class="text-link hover:underline"
          >Discord page</RouterLink
        >
      </p>
    </div>
    <fieldset class="flex flex-col gap-2">
      <legend class="mb-2 text-body-sm font-semibold text-ink">Sites</legend>
      <div class="flex flex-wrap gap-x-6 gap-y-3">
        <div v-for="site in options.sites" :key="site.name" class="flex items-center gap-3">
          <Checkbox
            :id="`site-${site.name}`"
            :model-value="pickedSites.includes(site.name)"
            @update:model-value="setSite(site.name, $event)"
          />
          <Label :for="`site-${site.name}`" class="cursor-pointer">{{ site.name }}</Label>
        </div>
      </div>
    </fieldset>
  </form>
</template>
