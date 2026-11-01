import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  hasConfigChanges,
  toConfigChanges,
  type ConfigSnapshot,
  type ConfigValues,
} from '@/modules/config/domain/entities/ScraperConfig'
import { requireConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'
import { toErrorMessage } from '@/shared/utils/errorMessage'
import type { LoadStatus } from '@/shared/utils/loadStatus'

const FALLBACK_ERROR_MESSAGE = 'Something went wrong. Try again.'

function copyValues(values: ConfigValues): ConfigValues {
  return {
    ...values,
    keywords: [...values.keywords],
    sites: values.sites.map((site) => ({ ...site })),
  }
}

export const useConfigStore = defineStore('config', () => {
  const status = ref<LoadStatus>('idle')
  const values = ref<ConfigValues | null>(null)
  const snapshot = ref<ConfigSnapshot | null>(null)
  const errorMessage = ref<string | null>(null)
  const saveError = ref<string | null>(null)
  const isSaving = ref(false)

  async function load(): Promise<void> {
    status.value = 'loading'
    errorMessage.value = null
    try {
      const next = await requireConfigUseCases().getConfig.execute()
      snapshot.value = next
      values.value = copyValues(next.values)
      status.value = 'ready'
    } catch (error) {
      errorMessage.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      status.value = 'error'
    }
  }

  async function save(): Promise<boolean> {
    const current = values.value
    const loaded = snapshot.value
    if (current === null || loaded === null || loaded.isReadOnly) {
      return false
    }
    const changes = toConfigChanges(current, loaded.values, loaded.locked)
    if (!hasConfigChanges(changes)) {
      return true
    }
    isSaving.value = true
    saveError.value = null
    try {
      await requireConfigUseCases().saveConfig.execute(changes)
      await load()
      return true
    } catch (error) {
      saveError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      return false
    } finally {
      isSaving.value = false
    }
  }

  return { status, values, snapshot, errorMessage, saveError, isSaving, load, save }
})
