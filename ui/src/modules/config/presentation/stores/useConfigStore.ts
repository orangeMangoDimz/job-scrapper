import { computed, ref, toRaw } from 'vue'
import { defineStore } from 'pinia'
import {
  hasConfigChanges,
  isSame,
  toConfigChanges,
  type ConfigSnapshot,
  type ConfigValues,
  type ConfigVersion,
} from '@/modules/config/domain/entities/ScraperConfig'
import { requireConfigUseCases } from '@/modules/config/presentation/stores/configUseCases'
import { toErrorMessage } from '@/shared/utils/errorMessage'
import type { LoadStatus } from '@/shared/utils/loadStatus'

const FALLBACK_ERROR_MESSAGE = 'Something went wrong. Try again.'

export const useConfigStore = defineStore('config', () => {
  const status = ref<LoadStatus>('idle')
  const values = ref<ConfigValues | null>(null)
  const snapshot = ref<ConfigSnapshot | null>(null)
  const history = ref<ConfigVersion[]>([])
  const errorMessage = ref<string | null>(null)
  const saveError = ref<string | null>(null)
  const historyError = ref<string | null>(null)
  const isSaving = ref(false)
  const isRestoring = ref(false)

  const isDirty = computed(
    () =>
      values.value !== null &&
      snapshot.value !== null &&
      !isSame(values.value, snapshot.value.values),
  )

  function discard(): void {
    if (snapshot.value === null) {
      return
    }
    values.value = structuredClone(toRaw(snapshot.value.values))
    saveError.value = null
  }

  async function load(): Promise<void> {
    status.value = 'loading'
    errorMessage.value = null
    try {
      const next = await requireConfigUseCases().getConfig.execute()
      snapshot.value = next
      values.value = structuredClone(next.values)
      status.value = 'ready'
    } catch (error) {
      errorMessage.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      status.value = 'error'
    }
  }

  async function loadHistory(): Promise<void> {
    historyError.value = null
    try {
      history.value = await requireConfigUseCases().getConfigHistory.execute()
    } catch (error) {
      historyError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
    }
  }

  async function save(): Promise<boolean> {
    const current = values.value
    const loaded = snapshot.value
    if (current === null || loaded === null || loaded.isStale) {
      return false
    }
    const changes = toConfigChanges(current, loaded.values)
    if (!hasConfigChanges(changes)) {
      return true
    }
    isSaving.value = true
    saveError.value = null
    try {
      await requireConfigUseCases().saveConfig.execute(changes, loaded.version)
      await Promise.all([load(), loadHistory()])
      return true
    } catch (error) {
      saveError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      return false
    } finally {
      isSaving.value = false
    }
  }

  async function restore(version: number): Promise<boolean> {
    const loaded = snapshot.value
    if (loaded === null || loaded.isStale) {
      return false
    }
    isRestoring.value = true
    saveError.value = null
    try {
      await requireConfigUseCases().restoreConfig.execute(version, loaded.version)
      await Promise.all([load(), loadHistory()])
      return true
    } catch (error) {
      saveError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      return false
    } finally {
      isRestoring.value = false
    }
  }

  return {
    status,
    values,
    snapshot,
    history,
    errorMessage,
    saveError,
    historyError,
    isSaving,
    isRestoring,
    isDirty,
    discard,
    load,
    loadHistory,
    save,
    restore,
  }
})
