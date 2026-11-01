import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'
import { env } from '@/core/config/env'

const LOG_STREAM_PATH = `${env.apiBaseUrl}/logs/stream`
const MAX_LINES = 500

export function useLiveLog(): { lines: Ref<string[]>; isConnected: Ref<boolean> } {
  const lines = ref<string[]>([])
  const isConnected = ref(false)
  let source: EventSource | null = null

  onMounted(() => {
    source = new EventSource(LOG_STREAM_PATH)
    source.onopen = () => {
      isConnected.value = true
    }
    source.onerror = () => {
      isConnected.value = false
    }
    source.onmessage = (event: MessageEvent<string>) => {
      lines.value = [...lines.value, event.data].slice(-MAX_LINES)
    }
  })

  onBeforeUnmount(() => {
    source?.close()
  })

  return { lines, isConnected }
}
