<script setup lang="ts">
import type { HTMLAttributes } from 'vue'

import { Menu } from '@lucide/vue'
import { cn } from '@/shared/utils/cn'
import { Button } from '@/shared/components/ui/button'
import { useSidebar } from './utils'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()

const { toggleSidebar } = useSidebar()
</script>

<template>
  <Button
    data-sidebar="trigger"
    data-slot="sidebar-trigger"
    variant="ghost"
    size="icon"
    :class="cn(props.class)"
    @click="toggleSidebar"
  >
    <Menu />
    <span class="sr-only">Open menu</span>
  </Button>
</template>
