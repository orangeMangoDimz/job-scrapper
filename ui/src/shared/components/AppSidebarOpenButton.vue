<script setup lang="ts">
import { PanelLeft } from '@lucide/vue'

import { Button } from '@/shared/components/ui/button'
</script>

<template>
  <Button
    data-slot="sidebar-open"
    variant="ghost"
    size="icon"
    class="fixed top-2 left-1 z-40 size-11 text-ink-muted hover:bg-surface hover:text-ink"
    aria-expanded="false"
  >
    <PanelLeft aria-hidden="true" />
    <span class="sr-only">Expand sidebar</span>
  </Button>
</template>
