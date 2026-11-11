<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { toast } from 'vue-sonner'
import { MAX_MESSAGE_CHARS, toSendSummary } from '@/modules/discord/domain/entities/Discord'
import DiscordJobPicker from '@/modules/discord/presentation/components/DiscordJobPicker.vue'
import DiscordMessagePreview from '@/modules/discord/presentation/components/DiscordMessagePreview.vue'
import DiscordSendResults from '@/modules/discord/presentation/components/DiscordSendResults.vue'
import {
  useDiscordComposeStore,
  type DiscordMode,
} from '@/modules/discord/presentation/stores/useDiscordComposeStore'
import { useDiscordSettingsStore } from '@/modules/discord/presentation/stores/useDiscordSettingsStore'
import { useRunStore } from '@/modules/runs/presentation/stores/useRunStore'
import EmptyState from '@/shared/components/EmptyState.vue'
import PageLoadState from '@/shared/components/PageLoadState.vue'
import PageSection from '@/shared/components/PageSection.vue'
import { Button } from '@/shared/components/ui/button'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { Label } from '@/shared/components/ui/label'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import { Textarea } from '@/shared/components/ui/textarea'

const MODE_LABELS: Record<DiscordMode, string> = {
  text: 'Free text',
  jobs: 'Scraper result',
}
const MODES = Object.keys(MODE_LABELS) as DiscordMode[]

const settingsStore = useDiscordSettingsStore()
const compose = useDiscordComposeStore()
const runStore = useRunStore()

const settings = computed(() => settingsStore.settings)
const isConfigured = computed(() => settings.value?.isConfigured === true)
const isComposePending = computed(
  () => compose.channels.length === 0 && compose.status !== 'ready' && compose.status !== 'error',
)
const channelGroups = computed(() => {
  const groups = new Map<string, typeof compose.channels>()
  for (const channel of compose.channels) {
    groups.set(channel.guildName, [...(groups.get(channel.guildName) ?? []), channel])
  }
  return [...groups.entries()]
})

function isMode(value: string | number): value is DiscordMode {
  return MODES.some((mode) => mode === value)
}

function changeMode(next: string | number): void {
  if (isMode(next)) {
    compose.mode = next
  }
}

function loadCompose(): Promise<void> {
  return settings.value === null ? Promise.resolve() : compose.load(settings.value)
}

async function loadPage(): Promise<void> {
  await settingsStore.load()
  if (isConfigured.value) {
    await loadCompose()
  }
}

watch(
  () => runStore.runs,
  (runs) => {
    if (runs.length > 0) {
      compose.runs = runs
    }
  },
)

async function send(): Promise<void> {
  const result = await compose.send()
  if (result === null) {
    if (compose.sendError !== null) {
      toast.error(compose.sendError)
    }
    return
  }
  const summary = toSendSummary(result)
  if (result.failed === 0) {
    toast.success(summary)
  } else if (result.sent === 0) {
    toast.error(summary)
  } else {
    toast.warning(summary)
  }
}

onMounted(() => void loadPage())
</script>

<template>
  <header class="flex flex-wrap items-start justify-between gap-3">
    <h2 id="discord-heading" class="min-w-0 text-title text-ink">Discord</h2>
  </header>

  <PageLoadState
    v-if="settings === null"
    :is-error="settingsStore.status === 'error'"
    loading-label="Loading Discord"
    error-title="Could not load Discord"
    :error-message="settingsStore.errorMessage"
    @retry="loadPage"
  >
    <div class="flex flex-col gap-6 md:gap-4">
      <Skeleton v-for="index in 2" :key="index" class="h-48 w-full rounded-lg" />
    </div>
  </PageLoadState>

  <EmptyState
    v-else-if="!isConfigured"
    title="Set up Discord in Config first"
    hint="Save a bot token there, then come back to send messages"
  >
    <template #action>
      <Button as-child variant="primary">
        <RouterLink to="/#config">Go to Config</RouterLink>
      </Button>
    </template>
  </EmptyState>

  <PageLoadState
    v-else-if="compose.status === 'error' || isComposePending"
    :is-error="compose.status === 'error'"
    loading-label="Loading channels and runs"
    error-title="Could not load Discord"
    :error-message="compose.errorMessage"
    @retry="loadCompose"
  >
    <div class="flex flex-col gap-6 md:gap-4">
      <Skeleton v-for="index in 2" :key="index" class="h-48 w-full rounded-lg" />
    </div>
  </PageLoadState>

  <form v-else class="flex min-w-0 flex-col gap-6 md:gap-4" @submit.prevent="send">
    <PageSection title="Destination">
      <div class="flex flex-col gap-4">
        <div class="flex flex-col gap-2">
          <Label for="discord-channel">Channel</Label>
          <Select
            :model-value="compose.channelId ?? undefined"
            :disabled="compose.channels.length === 0"
            @update:model-value="compose.channelId = String($event)"
          >
            <SelectTrigger id="discord-channel">
              <SelectValue placeholder="Pick a channel" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup v-for="[guildName, channels] in channelGroups" :key="guildName">
                <SelectLabel>{{ guildName }}</SelectLabel>
                <SelectItem v-for="channel in channels" :key="channel.id" :value="channel.id">
                  # {{ channel.name }}
                </SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
          <p v-if="compose.channels.length === 0" class="text-body-sm text-ink-muted">
            The bot cannot see any text channel yet. Invite it to a server first
          </p>
        </div>
        <div v-if="compose.hasMentionUser" class="flex items-center gap-3">
          <Checkbox
            id="discord-mention"
            :model-value="compose.mention"
            @update:model-value="compose.mention = $event === true"
          />
          <Label for="discord-mention" class="cursor-pointer">Mention user</Label>
        </div>
      </div>
    </PageSection>

    <PageSection title="Message">
      <Tabs :model-value="compose.mode" @update:model-value="changeMode">
        <TabsList aria-label="Message type">
          <TabsTrigger v-for="mode in MODES" :key="mode" :value="mode">
            {{ MODE_LABELS[mode] }}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="text">
          <div class="flex flex-col gap-2">
            <Label for="discord-text">Message</Label>
            <Textarea
              id="discord-text"
              v-model="compose.text"
              placeholder="Write a message"
              aria-describedby="discord-char-count"
            />
            <div class="flex flex-wrap items-center justify-between gap-3">
              <p v-if="compose.isOverLimit" role="alert" class="min-w-0 text-body-sm text-danger">
                A message can have at most {{ MAX_MESSAGE_CHARS }} characters, counting the mention
              </p>
              <p
                id="discord-char-count"
                aria-live="polite"
                :data-over="compose.isOverLimit ? 'true' : undefined"
                :class="[
                  'ml-auto text-body-sm tabular-nums',
                  compose.isOverLimit ? 'font-semibold text-danger' : 'text-ink-muted',
                ]"
              >
                {{ compose.charCount }} / {{ MAX_MESSAGE_CHARS }}
              </p>
            </div>
          </div>
        </TabsContent>
        <TabsContent value="jobs">
          <DiscordJobPicker
            :runs="compose.sendableRuns"
            :detail="compose.detail"
            :picked-indexes="compose.pickedIndexes"
            :is-loading="compose.isLoadingRun"
            :error="compose.runError"
            @select-run="compose.selectRun"
            @pick="compose.setJobPicked"
            @pick-all="compose.pickAllJobs"
            @clear="compose.clearJobs"
          />
        </TabsContent>
      </Tabs>
    </PageSection>

    <PageSection title="Preview">
      <template #actions>
        <Button type="button" size="sm" :disabled="!compose.canPreview" @click="compose.preview">
          {{ compose.isPreviewing ? 'Previewing' : 'Preview' }}
        </Button>
      </template>
      <p v-if="compose.previewError" role="alert" class="text-body-sm text-danger">
        {{ compose.previewError }}
      </p>
      <DiscordMessagePreview
        v-else-if="compose.previewMessages.length > 0"
        :messages="compose.previewMessages"
      />
      <p v-else class="text-body-sm text-ink-muted">Press Preview to see the messages</p>
    </PageSection>

    <DiscordSendResults v-if="compose.sendResult" :result="compose.sendResult" />

    <div
      data-slot="send-bar"
      class="sticky bottom-0 z-20 -mx-4 flex flex-wrap items-center justify-end gap-3 bg-surface px-4 py-3 md:mx-0"
    >
      <p v-if="compose.sendError" role="alert" class="mr-auto min-w-0 text-body-sm text-danger">
        {{ compose.sendError }}
      </p>
      <Button type="submit" variant="primary" :disabled="!compose.canSend">
        {{ compose.isSending ? 'Sending' : 'Send' }}
      </Button>
    </div>
  </form>
</template>
