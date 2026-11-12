<script setup lang="ts">
import { computed } from 'vue'
import type { RunRecord } from '@/modules/runs/domain/entities/Run'
import {
  DISCORD_TONE_CLASSES,
  toDiscordStatusView,
} from '@/modules/runs/presentation/components/runStatus'

const props = defineProps<{ record: RunRecord }>()

const view = computed(() => toDiscordStatusView(props.record))
</script>

<template>
  <span
    v-if="view"
    data-slot="discord-status"
    :data-tone="view.tone"
    :class="DISCORD_TONE_CLASSES[view.tone]"
  >
    {{ view.label }}
  </span>
</template>
