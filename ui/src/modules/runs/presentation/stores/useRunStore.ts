import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { RunDetail, RunOptions, RunRecord } from '@/modules/runs/domain/entities/Run'
import { requireRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'
import { toErrorMessage } from '@/shared/utils/errorMessage'
import type { LoadStatus } from '@/shared/utils/loadStatus'

export const POLL_INTERVAL_MS = 2000
export const MAX_POLL_FAILURES = 5
const FALLBACK_ERROR_MESSAGE = 'Something went wrong. Try again.'
const LOST_RUN_MESSAGE = 'Lost track of this run. Reload the page to check it.'
const HISTORY_ERROR_MESSAGE = 'Could not refresh the run history.'

export const useRunStore = defineStore('runs', () => {
  const status = ref<LoadStatus>('idle')
  const options = ref<RunOptions | null>(null)
  const runs = ref<RunRecord[]>([])
  const selected = ref<RunDetail | null>(null)
  const activeRunId = ref<string | null>(null)
  const errorMessage = ref<string | null>(null)
  const actionError = ref<string | null>(null)
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let pollGeneration = 0
  let pollFailures = 0

  const isRunning = computed(() => activeRunId.value !== null)

  async function refreshHistory(): Promise<void> {
    try {
      runs.value = await requireRunUseCases().listRuns.execute()
    } catch {
      actionError.value = HISTORY_ERROR_MESSAGE
    }
  }

  function schedulePoll(id: string): void {
    const generation = pollGeneration
    pollTimer = setTimeout(() => void poll(id, generation), POLL_INTERVAL_MS)
  }

  function followRun(id: string): void {
    activeRunId.value = id
    pollFailures = 0
    schedulePoll(id)
  }

  function handlePollFailure(id: string): void {
    pollFailures += 1
    if (pollFailures < MAX_POLL_FAILURES) {
      schedulePoll(id)
      return
    }
    actionError.value = LOST_RUN_MESSAGE
    activeRunId.value = null
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

  async function poll(id: string, generation: number): Promise<void> {
    let detail: RunDetail
    try {
      detail = await requireRunUseCases().getRun.execute(id)
    } catch {
      if (generation === pollGeneration) {
        handlePollFailure(id)
      }
      return
    }
    if (generation !== pollGeneration) {
      return
    }
    pollFailures = 0
    if (detail.record.status === 'running') {
      schedulePoll(id)
      return
    }
    selected.value = detail
    activeRunId.value = null
    await refreshHistory()
  }

  async function start(keywords: string[], sites: string[]): Promise<void> {
    actionError.value = null
    try {
      const record = await requireRunUseCases().startRun.execute(keywords, sites)
      followRun(record.id)
      await refreshHistory()
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
    pollGeneration += 1
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
