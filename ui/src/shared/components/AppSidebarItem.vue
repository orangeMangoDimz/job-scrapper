<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import type { NavItem } from '@/shared/components/types'
import { SidebarMenuButton, SidebarMenuItem, useSidebar } from '@/shared/components/ui/sidebar'

const props = defineProps<{
  item: NavItem
}>()

const route = useRoute()
const { isMobile, setOpenMobile } = useSidebar()

function closeOnMobile(): void {
  if (isMobile.value) {
    setOpenMobile(false)
  }
}

const currentPath = computed(() => {
  const trimmed = route.path.replace(/\/+$/, '')
  return trimmed === '' ? '/' : trimmed
})

const isCurrent = computed(
  () => currentPath.value === props.item.to || currentPath.value.startsWith(`${props.item.to}/`),
)

const ariaCurrent = computed(() => {
  if (!isCurrent.value) {
    return undefined
  }
  return currentPath.value === props.item.to ? 'page' : 'true'
})
</script>

<template>
  <SidebarMenuItem>
    <SidebarMenuButton as-child :is-active="isCurrent" :tooltip="item.label">
      <RouterLink :to="item.to" :aria-current="ariaCurrent" @click="closeOnMobile">
        <component :is="item.icon" />
        <span class="sidebar-fade truncate">{{ item.label }}</span>
      </RouterLink>
    </SidebarMenuButton>
  </SidebarMenuItem>
</template>
