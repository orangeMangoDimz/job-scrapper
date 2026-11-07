<script setup lang="ts">
import { Monitor, Moon, Sun } from '@lucide/vue'
import { computed, type Component } from 'vue'

import ThemeMenuGroup from '@/shared/components/ThemeMenuGroup.vue'
import { Button } from '@/shared/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/shared/components/ui/dropdown-menu'
import { useThemeStore } from '@/shared/stores/useThemeStore'
import { THEME_MODE_LABELS, type ThemeMode } from '@/shared/utils/theme'

const MODE_ICONS: Record<ThemeMode, Component> = {
  light: Sun,
  dark: Moon,
  system: Monitor,
}

const theme = useThemeStore()
const triggerLabel = computed(() => `Theme: ${THEME_MODE_LABELS[theme.mode]}`)
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button variant="ghost" size="icon-lg" :aria-label="triggerLabel">
        <component :is="MODE_ICONS[theme.mode]" aria-hidden="true" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" aria-label="Theme">
      <ThemeMenuGroup />
    </DropdownMenuContent>
  </DropdownMenu>
</template>
