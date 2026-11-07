<script setup lang="ts">
import { Monitor, Moon, Sun } from '@lucide/vue'
import type { AcceptableValue } from 'reka-ui'
import { useId, type Component } from 'vue'

import { useThemeStore } from '@/shared/stores/useThemeStore'
import {
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
} from '@/shared/components/ui/dropdown-menu'
import { isThemeMode, THEME_MODE_LABELS, THEME_MODES, type ThemeMode } from '@/shared/utils/theme'

const MODE_ICONS: Record<ThemeMode, Component> = {
  light: Sun,
  dark: Moon,
  system: Monitor,
}

const emit = defineEmits<{
  change: [mode: ThemeMode]
}>()

const theme = useThemeStore()
const labelId = useId()

function select(value: AcceptableValue): void {
  if (!isThemeMode(value) || value === theme.mode) {
    return
  }
  theme.setMode(value)
  emit('change', value)
}
</script>

<template>
  <DropdownMenuLabel :id="labelId">Theme</DropdownMenuLabel>
  <DropdownMenuRadioGroup
    data-slot="theme-menu-group"
    :aria-labelledby="labelId"
    :model-value="theme.mode"
    @update:model-value="select"
  >
    <DropdownMenuRadioItem v-for="mode in THEME_MODES" :key="mode" :value="mode">
      <component :is="MODE_ICONS[mode]" aria-hidden="true" />
      {{ THEME_MODE_LABELS[mode] }}
    </DropdownMenuRadioItem>
  </DropdownMenuRadioGroup>
</template>
