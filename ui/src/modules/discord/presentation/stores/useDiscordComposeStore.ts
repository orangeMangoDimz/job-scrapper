import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import {
  countChars,
  MAX_JOBS_PER_SEND,
  MAX_MESSAGE_CHARS,
  toMentionPrefix,
  type DiscordChannel,
  type DiscordContent,
  type DiscordSendResult,
  type DiscordSettings,
} from '@/modules/discord/domain/entities/Discord'
import { requireDiscordUseCases } from '@/modules/discord/presentation/stores/discordUseCases'
import type { RunDetail, RunRecord } from '@/modules/runs/domain/entities/Run'
import { requireRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'
import { toErrorMessage } from '@/shared/utils/errorMessage'
import type { LoadStatus } from '@/shared/utils/loadStatus'

export type DiscordMode = 'text' | 'jobs'

const FALLBACK_ERROR_MESSAGE = 'Something went wrong. Try again.'

export const useDiscordComposeStore = defineStore('discordCompose', () => {
  const status = ref<LoadStatus>('idle')
  const channels = ref<DiscordChannel[]>([])
  const runs = ref<RunRecord[]>([])
  const detail = ref<RunDetail | null>(null)
  const mentionUserId = ref<string | null>(null)
  const channelId = ref<string | null>(null)
  const mention = ref(true)
  const mode = ref<DiscordMode>('text')
  const text = ref('')
  const pickedIndexes = ref<number[]>([])
  const previewMessages = ref<string[]>([])
  const sendResult = ref<DiscordSendResult | null>(null)
  const errorMessage = ref<string | null>(null)
  const runError = ref<string | null>(null)
  const previewError = ref<string | null>(null)
  const sendError = ref<string | null>(null)
  const isLoadingRun = ref(false)
  const isPreviewing = ref(false)
  const isSending = ref(false)
  let runRequestId = 0
  let previewRequestId = 0

  const hasMentionUser = computed(() => mentionUserId.value !== null)
  const isMentioned = computed(() => hasMentionUser.value && mention.value)
  const sendableRuns = computed(() => runs.value.filter((run) => run.jobCount > 0))
  const mentionPrefix = computed(() => toMentionPrefix(mentionUserId.value, isMentioned.value))
  const charCount = computed(() => countChars(mentionPrefix.value) + countChars(text.value))
  const isOverLimit = computed(() =>
    mode.value === 'text'
      ? charCount.value > MAX_MESSAGE_CHARS
      : pickedIndexes.value.length > MAX_JOBS_PER_SEND,
  )
  const content = computed<DiscordContent | null>(() => {
    if (isOverLimit.value) {
      return null
    }
    if (mode.value === 'text') {
      return text.value.trim() === '' ? null : { kind: 'text', text: text.value }
    }
    if (detail.value === null || pickedIndexes.value.length === 0) {
      return null
    }
    return {
      kind: 'jobs',
      runId: detail.value.record.id,
      jobIndexes: [...pickedIndexes.value].sort((first, second) => first - second),
    }
  })
  const canPreview = computed(() => content.value !== null && !isPreviewing.value)
  const canSend = computed(
    () =>
      content.value !== null &&
      channelId.value !== null &&
      !isLoadingRun.value &&
      !isPreviewing.value &&
      !isSending.value,
  )

  watch(
    [content, isMentioned],
    () => {
      previewRequestId += 1
      isPreviewing.value = false
      previewMessages.value = []
      previewError.value = null
    },
    { flush: 'sync' },
  )

  async function load(settings: DiscordSettings): Promise<void> {
    status.value = 'loading'
    errorMessage.value = null
    try {
      const [nextChannels, nextRuns] = await Promise.all([
        requireDiscordUseCases().listChannels.execute(),
        requireRunUseCases().listRuns.execute(),
      ])
      channels.value = nextChannels
      runs.value = nextRuns
      mentionUserId.value = settings.mentionUserId
      mention.value = true
      channelId.value = nextChannels.some((channel) => channel.id === settings.defaultChannelId)
        ? settings.defaultChannelId
        : null
      status.value = 'ready'
    } catch (error) {
      errorMessage.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      status.value = 'error'
    }
  }

  async function selectRun(id: string): Promise<void> {
    runRequestId += 1
    const requestId = runRequestId
    isLoadingRun.value = true
    runError.value = null
    try {
      const next = await requireRunUseCases().getRun.execute(id)
      if (requestId !== runRequestId) {
        return
      }
      detail.value = next
      pickedIndexes.value = next.jobs.slice(0, MAX_JOBS_PER_SEND).map((_, index) => index)
    } catch (error) {
      if (requestId !== runRequestId) {
        return
      }
      detail.value = null
      pickedIndexes.value = []
      runError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
    } finally {
      if (requestId === runRequestId) {
        isLoadingRun.value = false
      }
    }
  }

  function setJobPicked(index: number, isPicked: boolean): void {
    const rest = pickedIndexes.value.filter((picked) => picked !== index)
    pickedIndexes.value = isPicked ? [...rest, index].sort((first, second) => first - second) : rest
  }

  function pickAllJobs(): void {
    pickedIndexes.value = detail.value?.jobs.map((_, index) => index) ?? []
  }

  function clearJobs(): void {
    pickedIndexes.value = []
  }

  async function preview(): Promise<void> {
    const current = content.value
    if (current === null) {
      return
    }
    previewRequestId += 1
    const requestId = previewRequestId
    isPreviewing.value = true
    previewError.value = null
    try {
      const messages = await requireDiscordUseCases().previewMessage.execute(
        isMentioned.value,
        current,
      )
      if (requestId === previewRequestId) {
        previewMessages.value = messages
      }
    } catch (error) {
      if (requestId === previewRequestId) {
        previewMessages.value = []
        previewError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      }
    } finally {
      if (requestId === previewRequestId) {
        isPreviewing.value = false
      }
    }
  }

  async function send(): Promise<DiscordSendResult | null> {
    const current = content.value
    const channel = channelId.value
    if (current === null || channel === null || isSending.value) {
      return null
    }
    isSending.value = true
    sendError.value = null
    sendResult.value = null
    try {
      sendResult.value = await requireDiscordUseCases().sendMessage.execute(
        channel,
        isMentioned.value,
        current,
      )
      return sendResult.value
    } catch (error) {
      sendError.value = toErrorMessage(error, FALLBACK_ERROR_MESSAGE)
      return null
    } finally {
      isSending.value = false
    }
  }

  return {
    status,
    channels,
    runs,
    detail,
    channelId,
    mention,
    mode,
    text,
    pickedIndexes,
    previewMessages,
    sendResult,
    errorMessage,
    runError,
    previewError,
    sendError,
    isLoadingRun,
    isPreviewing,
    isSending,
    hasMentionUser,
    sendableRuns,
    charCount,
    isOverLimit,
    canPreview,
    canSend,
    load,
    selectRun,
    setJobPicked,
    pickAllJobs,
    clearJobs,
    preview,
    send,
  }
})
