<script setup lang="ts">
import { ChevronUp, LogOut, PanelLeft, ShieldUser } from '@lucide/vue'
import { computed, nextTick, ref, watch, type ComponentPublicInstance } from 'vue'

import type { NavGroup } from '@/shared/components/types'
import AppSidebarItem from '@/shared/components/AppSidebarItem.vue'
import AppSidebarOpenButton from '@/shared/components/AppSidebarOpenButton.vue'
import SignOutConfirmDialog from '@/shared/components/SignOutConfirmDialog.vue'
import ThemeMenuGroup from '@/shared/components/ThemeMenuGroup.vue'
import { Button } from '@/shared/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/components/ui/dropdown-menu'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  useSidebar,
} from '@/shared/components/ui/sidebar'
import { THEME_MODE_LABELS, type ThemeMode } from '@/shared/utils/theme'

defineProps<{
  groups: NavGroup[]
  canSignOut: boolean
}>()

defineEmits<{
  signOut: []
}>()

const isSignOutDialogOpen = ref(false)
const adminTrigger = ref<InstanceType<typeof DropdownMenuTrigger> | null>(null)
const adminAnchor = ref<HTMLElement | null>(null)
const sidebarToggle = ref<InstanceType<typeof Button> | null>(null)
const sidebarOpenButton = ref<InstanceType<typeof AppSidebarOpenButton> | null>(null)
const themeAnnouncement = ref('')
const { isMobile, state, toggleSidebar } = useSidebar()

const isHidden = computed(() => !isMobile.value && state.value === 'collapsed')

function focusButton(button: ComponentPublicInstance | null): void {
  const element = button?.$el as HTMLElement | undefined
  element?.focus()
}

watch(isSignOutDialogOpen, (isOpen) => {
  if (!isOpen) {
    void nextTick(() => focusButton(adminTrigger.value))
  }
})

async function collapseSidebar(): Promise<void> {
  toggleSidebar()
  await nextTick()
  focusButton(sidebarOpenButton.value)
}

async function expandSidebar(): Promise<void> {
  toggleSidebar()
  await nextTick()
  focusButton(sidebarToggle.value)
}

function announceTheme(mode: ThemeMode): void {
  themeAnnouncement.value = `Theme changed to ${THEME_MODE_LABELS[mode]}`
}

function requestSignOut(): void {
  void nextTick(() => {
    isSignOutDialogOpen.value = true
  })
}
</script>

<template>
  <AppSidebarOpenButton v-if="isHidden" ref="sidebarOpenButton" @click="expandSidebar" />
  <Sidebar collapsible="offcanvas" :inert="isHidden || undefined">
    <SidebarHeader class="flex-row items-center gap-0">
      <span
        class="sidebar-fade min-w-0 flex-1 overflow-hidden pl-3 text-heading font-bold text-ink"
      >
        NoNo Scraper
      </span>
      <Button
        v-if="!isMobile"
        ref="sidebarToggle"
        data-slot="sidebar-toggle"
        variant="ghost"
        size="icon"
        class="size-11 shrink-0 text-ink-muted hover:bg-surface hover:text-ink"
        aria-expanded="true"
        @click="collapseSidebar"
      >
        <PanelLeft aria-hidden="true" />
        <span class="sr-only">Collapse sidebar</span>
      </Button>
    </SidebarHeader>

    <SidebarContent as="nav" aria-label="Main">
      <SidebarGroup v-for="group in groups" :key="group.id">
        <SidebarGroupLabel v-if="group.label">
          {{ group.label }}
        </SidebarGroupLabel>
        <SidebarMenu>
          <AppSidebarItem v-for="item in group.items" :key="item.id" :item="item" />
        </SidebarMenu>
      </SidebarGroup>
    </SidebarContent>

    <SidebarFooter>
      <span class="sr-only" role="status" aria-live="polite" data-slot="theme-announcement">{{
        themeAnnouncement
      }}</span>
      <div ref="adminAnchor" data-slot="sidebar-account">
        <DropdownMenu>
          <DropdownMenuTrigger
            ref="adminTrigger"
            class="group/account flex w-full cursor-pointer items-center gap-3 overflow-hidden rounded-md bg-accent-soft p-3 text-left outline-none focus-visible:focus-ring"
          >
            <span
              aria-hidden="true"
              class="flex size-10 shrink-0 items-center justify-center rounded-full bg-accent text-on-accent"
            >
              <ShieldUser class="size-5" />
            </span>
            <span class="sidebar-collapse min-w-32 flex-1">
              <span class="flex flex-col">
                <span class="text-body-sm font-semibold text-accent">Admin</span>
                <span class="text-body-sm text-ink-muted">Theme and session</span>
              </span>
            </span>
            <span class="sidebar-fade flex shrink-0">
              <ChevronUp
                class="size-5 text-ink-muted transition-transform duration-150 group-data-[state=open]/account:rotate-180"
                aria-hidden="true"
              />
            </span>
            <span class="sr-only">Admin menu</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            side="top"
            align="start"
            :reference="adminAnchor ?? undefined"
            aria-label="Admin"
          >
            <ThemeMenuGroup @change="announceTheme" />
            <template v-if="canSignOut">
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="danger" @select="requestSignOut">
                <LogOut aria-hidden="true" />
                Sign out
              </DropdownMenuItem>
            </template>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </SidebarFooter>
    <SignOutConfirmDialog v-model:open="isSignOutDialogOpen" @confirm="$emit('signOut')" />
  </Sidebar>
</template>
