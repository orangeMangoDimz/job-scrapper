import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { RunDetail, RunOptions, RunRecord } from '@/modules/runs/domain/entities/Run'
import { requireRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'
import { toErrorMessage } from '@/shared/utils/errorMessage'
import type { LoadStatus } from '@/shared/utils/loadStatus'

export const POLL_INTERVAL_MS = 2000
const FALLBACK_ERROR_MESSAGE = 'Something went wrong. Try again.'

export const useRunStore = defineStore('runs', () => {
  const status = ref<LoadStatus>('idle')
  const options = ref<RunOptions | null>(null)
  const runs = ref<RunRecord[]>([])
  const selected = ref<RunDetail | null>(null)
  const activeRunId = ref<string | null>(null)
  const errorMessage = ref<string | null>(null)
  const actionError = ref<string | null>(null)
  let pollTimer: ReturnType<typeof setTimeout> | null = null

  const isRunning = computed(() => activeRunId.value !== null)

  async function refreshHistory(): Promise<void> {
    runs.value = await requireRunUseCases().listRuns.execute()
  }

  function followRun(id: string): void {
    activeRunId.value = id
    pollTimer = setTimeout(() => void poll(id), POLL_INTERVAL_MS)
  }

  async function load(): Promise<void> {
    status.value = 'loading'
    errorMessage.value = null
    try {
      const useCases = requireRunUseCases()
      const [nextOptions, nextRuns] = await Promise.all([
        useCases.getOptions.execute(),
        useCases.listRuns.execute(),
      ])
      options.value = nextOptions
      runs.value = nextRuns
      status.value = 'ready'
      const active = nextRuns.find((run) => run.status === 'running')
      if (active !== undefined && activeRunId.value === null) {
        followRun(active.id)
      }
    } catch (error) {
      errorMessage.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      status.value = 'error'
    }
  }

  async function poll(id: string): Promise<void> {
    try {
      const detail = await requireRunUseCases().getRun.execute(id)
      if (detail.record.status === 'running') {
        followRun(id)
        return
      }
      selected.value = detail
      activeRunId.value = null
      await refreshHistory()
    } catch (error) {
      actionError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      activeRunId.value = null
    }
  }

  async function start(keywords: string[], sites: string[]): Promise<void> {
    actionError.value = null
    try {
      const record = await requireRunUseCases().startRun.execute(keywords, sites)
      await refreshHistory()
      followRun(record.id)
    } catch (error) {
      actionError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
    }
  }

  async function select(id: string): Promise<void> {
    try {
      selected.value = await requireRunUseCases().getRun.execute(id)
    } catch (error) {
      actionError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
    }
  }

  function stopPolling(): void {
    if (pollTimer !== null) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
    activeRunId.value = null
  }

  return {
    status,
    options,
    runs,
    selected,
    errorMessage,
    actionError,
    isRunning,
    load,
    start,
    select,
    stopPolling,
  }
})
