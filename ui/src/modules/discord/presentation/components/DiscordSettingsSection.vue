<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  MAX_MESSAGE_CHARS,
  toSettingsChanges,
  toSettingsForm,
  type DiscordSettingsForm,
} from '@/modules/discord/domain/entities/Discord'
import { useDiscordSettingsStore } from '@/modules/discord/presentation/stores/useDiscordSettingsStore'
import PageLoadState from '@/shared/components/PageLoadState.vue'
import PageSection from '@/shared/components/PageSection.vue'
import PasswordInput from '@/shared/components/PasswordInput.vue'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { Textarea } from '@/shared/components/ui/textarea'

const SAVED_MESSAGE = 'Discord settings saved'
const TOKEN_PLACEHOLDER = 'Bot token'
const ID_PATTERN = '[0-9]{17,20}'

const store = useDiscordSettingsStore()
const form = ref<DiscordSettingsForm | null>(null)
const tokenPlaceholder = computed(() => store.settings?.tokenHint ?? TOKEN_PLACEHOLDER)

watch(
  () => store.settings,
  (settings) => {
    form.value = settings === null ? null : toSettingsForm(settings)
  },
  { immediate: true },
)

async function save(): Promise<void> {
  if (form.value === null || store.settings === null) {
    return
  }
  if (await store.save(toSettingsChanges(form.value, store.settings))) {
    toast.success(SAVED_MESSAGE)
  }
}

onMounted(() => {
  if (store.settings === null) {
    void store.load()
  }
})
</script>

<template>
  <PageSection title="Bot settings">
    <PageLoadState
      v-if="form === null"
      :is-error="store.status === 'error'"
      loading-label="Loading Discord settings"
      error-title="Could not load Discord settings"
      :error-message="store.errorMessage"
      @retry="store.load"
    >
      <Skeleton v-for="index in 3" :key="index" class="h-10 w-full" />
    </PageLoadState>

    <form v-else class="flex flex-col gap-4" @submit.prevent="save">
      <PasswordInput
        id="discord-token"
        v-model="form.token"
        label="Bot token"
        :placeholder="tokenPlaceholder"
        hint="Leave empty to keep the current token. It is never shown again"
        autocomplete="off"
      />
      <div class="grid gap-4 sm:grid-cols-2">
        <div class="flex flex-col gap-2">
          <Label for="discord-default-channel">Default channel ID</Label>
          <Input
            id="discord-default-channel"
            v-model="form.defaultChannelId"
            placeholder="Default channel ID"
            inputmode="numeric"
            :pattern="ID_PATTERN"
            title="17 to 20 digits"
            autocomplete="off"
          />
        </div>
        <div class="flex flex-col gap-2">
          <Label for="discord-mention-user">Mention user ID</Label>
          <Input
            id="discord-mention-user"
            v-model="form.mentionUserId"
            placeholder="Mention user ID"
            inputmode="numeric"
            :pattern="ID_PATTERN"
            title="17 to 20 digits"
            autocomplete="off"
          />
        </div>
      </div>
      <div class="flex flex-col gap-2">
        <Label for="discord-template">Message template</Label>
        <Textarea
          id="discord-template"
          v-model="form.messageTemplate"
          placeholder="Message template"
          required
        />
        <p class="text-body-sm text-ink-muted">
          Use {title}, {company}, {location} and {url}. A missing field stays empty
        </p>
      </div>
      <div class="flex flex-col gap-2 sm:max-w-48">
        <Label for="discord-max-chars">Max characters per message</Label>
        <Input
          id="discord-max-chars"
          v-model="form.maxChars"
          placeholder="Max characters"
          type="number"
          required
          min="1"
          :max="MAX_MESSAGE_CHARS"
        />
      </div>
      <div class="flex flex-wrap items-center justify-end gap-3">
        <p
          v-if="store.bot"
          role="status"
          class="mr-auto min-w-0 text-body-sm font-semibold text-accent"
        >
          Connected as {{ store.bot.name }}
        </p>
        <p v-if="store.testError" role="alert" class="mr-auto min-w-0 text-body-sm text-danger">
          {{ store.testError }}
        </p>
        <p v-if="store.saveError" role="alert" class="mr-auto min-w-0 text-body-sm text-danger">
          {{ store.saveError }}
        </p>
        <Button
          type="button"
          :disabled="store.isTesting || !store.settings?.isConfigured"
          @click="store.testConnection"
        >
          {{ store.isTesting ? 'Testing' : 'Test connection' }}
        </Button>
        <Button type="submit" variant="primary" :disabled="store.isSaving">
          {{ store.isSaving ? 'Saving' : 'Save' }}
        </Button>
      </div>
    </form>
  </PageSection>
</template>
