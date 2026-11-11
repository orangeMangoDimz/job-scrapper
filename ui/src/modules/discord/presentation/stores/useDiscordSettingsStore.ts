import { ref } from 'vue'
import { defineStore } from 'pinia'
import type {
  DiscordBot,
  DiscordSettings,
  DiscordSettingsChanges,
} from '@/modules/discord/domain/entities/Discord'
import { requireDiscordUseCases } from '@/modules/discord/presentation/stores/discordUseCases'
import { toErrorMessage } from '@/shared/utils/errorMessage'
import type { LoadStatus } from '@/shared/utils/loadStatus'

const FALLBACK_ERROR_MESSAGE = 'Something went wrong. Try again.'

export const useDiscordSettingsStore = defineStore('discordSettings', () => {
  const status = ref<LoadStatus>('idle')
  const settings = ref<DiscordSettings | null>(null)
  const bot = ref<DiscordBot | null>(null)
  const errorMessage = ref<string | null>(null)
  const saveError = ref<string | null>(null)
  const testError = ref<string | null>(null)
  const isSaving = ref(false)
  const isTesting = ref(false)

  async function load(): Promise<void> {
    status.value = 'loading'
    errorMessage.value = null
    try {
      settings.value = await requireDiscordUseCases().getSettings.execute()
      status.value = 'ready'
    } catch (error) {
      errorMessage.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      status.value = 'error'
    }
  }

  async function save(changes: DiscordSettingsChanges): Promise<boolean> {
    isSaving.value = true
    saveError.value = null
    try {
      settings.value = await requireDiscordUseCases().saveSettings.execute(changes)
      status.value = 'ready'
      bot.value = null
      testError.value = null
      return true
    } catch (error) {
      saveError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      return false
    } finally {
      isSaving.value = false
    }
  }

  async function testConnection(): Promise<boolean> {
    isTesting.value = true
    testError.value = null
    bot.value = null
    try {
      bot.value = await requireDiscordUseCases().testConnection.execute()
      return true
    } catch (error) {
      testError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      return false
    } finally {
      isTesting.value = false
    }
  }

  return {
    status,
    settings,
    bot,
    errorMessage,
    saveError,
    testError,
    isSaving,
    isTesting,
    load,
    save,
    testConnection,
  }
})
