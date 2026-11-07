<script setup lang="ts">
import { PanelLeft } from '@lucide/vue'
import { computed } from 'vue'

import { Button } from '@/shared/components/ui/button'
import { useSidebar } from '@/shared/components/ui/sidebar'

const { state, toggleSidebar } = useSidebar()

const isExpanded = computed(() => state.value === 'expanded')
</script>

<template>
  <Button
    data-slot="sidebar-toggle"
    variant="ghost"
    size="icon"
    class="size-11 text-ink-muted hover:bg-surface-subtle hover:text-ink"
    :aria-expanded="isExpanded ? 'true' : 'false'"
    @click="toggleSidebar"
  >
    <PanelLeft aria-hidden="true" />
    <span class="sr-only">{{ isExpanded ? 'Collapse sidebar' : 'Expand sidebar' }}</span>
  </Button>
</template>
