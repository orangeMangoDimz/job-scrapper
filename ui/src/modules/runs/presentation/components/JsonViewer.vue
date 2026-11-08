<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { CheckIcon, CopyIcon } from '@lucide/vue'
import type { JsonObject } from '@/modules/runs/domain/entities/Run'
import {
  MAX_HIGHLIGHT_CHARS,
  prettyJson,
  tokenizeJson,
  type JsonTokenKind,
} from '@/modules/runs/presentation/components/jsonTokens'
import { formatJobCount } from '@/modules/runs/presentation/components/runStatus'
import { Button } from '@/shared/components/ui/button'

type CopyState = 'idle' | 'copied' | 'failed'

const FEEDBACK_MS = 2000
const TOKEN_CLASSES: Record<JsonTokenKind, string> = {
  key: 'text-syntax-key',
  string: 'text-syntax-string',
  number: 'text-syntax-number',
  literal: 'font-semibold text-syntax-literal',
  punct: 'text-ink-muted',
  plain: '',
}
const COPY_LABELS: Record<CopyState, string> = {
  idle: 'Copy',
  copied: 'Copied',
  failed: 'Copy failed',
}

const props = defineProps<{ value: JsonObject; jobCount?: number | null }>()

const text = computed(() => prettyJson(props.value))
const isHighlighted = computed(() => text.value.length <= MAX_HIGHLIGHT_CHARS)
const tokens = computed(() => (isHighlighted.value ? tokenizeJson(text.value) : []))

const copyState = ref<CopyState>('idle')
let resetTimer: ReturnType<typeof setTimeout> | null = null

function showCopyState(next: CopyState): void {
  copyState.value = next
  if (resetTimer !== null) {
    clearTimeout(resetTimer)
  }
  resetTimer = setTimeout(() => {
    copyState.value = 'idle'
    resetTimer = null
  }, FEEDBACK_MS)
}

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(text.value)
    showCopyState('copied')
  } catch {
    showCopyState('failed')
  }
}

onBeforeUnmount(() => {
  if (resetTimer !== null) {
    clearTimeout(resetTimer)
  }
})
</script>

<template>
  <div class="flex min-w-0 flex-col gap-2">
    <div class="flex items-center gap-3">
      <p
        v-if="jobCount !== null && jobCount !== undefined"
        data-slot="json-count"
        class="text-body-sm text-ink-muted"
      >
        {{ formatJobCount(jobCount) }}
      </p>
      <Button data-slot="json-copy" size="sm" class="ml-auto" @click="copy">
        <CheckIcon v-if="copyState === 'copied'" aria-hidden="true" />
        <CopyIcon v-else aria-hidden="true" />
        {{ COPY_LABELS[copyState] }}
      </Button>
    </div>
    <p v-if="copyState === 'failed'" role="status" class="text-body-sm text-danger">
      Could not copy. Select the text and copy it by hand.
    </p>
    <div
      data-slot="json-scroll"
      tabindex="0"
      role="region"
      aria-label="JSON output"
      class="max-h-96 overflow-auto rounded-md border border-line bg-surface-subtle p-4 outline-none focus-visible:focus-ring"
    >
      <pre
        class="font-mono text-code whitespace-pre text-ink"
      ><code v-if="!isHighlighted">{{ text }}</code><code v-else><template
        v-for="(token, index) in tokens"
        :key="index"
      ><span v-if="token.kind === 'plain'">{{ token.text }}</span><span
        v-else
        :data-token="token.kind"
        :class="TOKEN_CLASSES[token.kind]"
      >{{ token.text }}</span></template></code></pre>
    </div>
  </div>
</template>
