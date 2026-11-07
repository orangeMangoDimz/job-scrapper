<script setup lang="ts">
import type { SidebarProps } from '.'
import { cn } from '@/shared/utils/cn'
import { Sheet, SheetContent } from '@/shared/components/ui/sheet'
import SheetDescription from '@/shared/components/ui/sheet/SheetDescription.vue'
import SheetHeader from '@/shared/components/ui/sheet/SheetHeader.vue'
import SheetTitle from '@/shared/components/ui/sheet/SheetTitle.vue'
import { SIDEBAR_WIDTH_MOBILE, useSidebar } from './utils'

defineOptions({
  inheritAttrs: false,
})

const props = withDefaults(defineProps<SidebarProps>(), {
  side: 'left',
  variant: 'sidebar',
  collapsible: 'offcanvas',
})

const { isMobile, state, openMobile, setOpenMobile } = useSidebar()
</script>

<template>
  <div
    v-if="collapsible === 'none'"
    data-slot="sidebar"
    :class="
      cn(
        'flex w-(--sidebar-width) flex-col gap-8 bg-surface-subtle px-4 py-6 text-ink',
        props.class,
      )
    "
    v-bind="$attrs"
  >
    <slot />
  </div>

  <Sheet v-else-if="isMobile" :open="openMobile" v-bind="$attrs" @update:open="setOpenMobile">
    <SheetContent
      data-sidebar="sidebar"
      data-slot="sidebar"
      data-mobile="true"
      :side="side"
      class="gap-0 bg-surface-subtle p-0 text-ink data-[side=left]:w-(--sidebar-width) data-[side=right]:w-(--sidebar-width)"
      :style="{
        '--sidebar-width': SIDEBAR_WIDTH_MOBILE,
      }"
    >
      <SheetHeader class="sr-only">
        <SheetTitle>Sidebar</SheetTitle>
        <SheetDescription>Displays the mobile sidebar.</SheetDescription>
      </SheetHeader>
      <div class="flex h-full w-full flex-col gap-8 px-4 py-6">
        <slot />
      </div>
    </SheetContent>
  </Sheet>

  <div
    v-else
    class="group peer hidden text-ink md:block"
    data-slot="sidebar"
    :data-state="state"
    :data-collapsible="state === 'collapsed' ? collapsible : ''"
    :data-variant="variant"
    :data-side="side"
  >
    <div
      data-slot="sidebar-gap"
      :class="
        cn(
          'relative w-(--sidebar-width) bg-transparent transition-[width] duration-220 ease-out',
          'group-data-[collapsible=offcanvas]:w-0',
          'group-data-[side=right]:rotate-180',
          variant === 'floating' || variant === 'inset'
            ? 'group-data-[collapsible=icon]:w-[calc(var(--sidebar-width-icon)+(--spacing(4)))]'
            : 'group-data-[collapsible=icon]:w-(--sidebar-width-icon)',
        )
      "
    />
    <div
      data-slot="sidebar-container"
      :data-side="side"
      :class="
        cn(
          'fixed inset-y-0 z-10 hidden h-svh w-(--sidebar-width) transition-[translate,width] duration-220 ease-out md:flex',
          side === 'left'
            ? 'left-0 group-data-[collapsible=offcanvas]:-translate-x-full'
            : 'right-0 group-data-[collapsible=offcanvas]:translate-x-full',
          variant === 'floating' || variant === 'inset'
            ? 'p-2 group-data-[collapsible=icon]:w-[calc(var(--sidebar-width-icon)+(--spacing(4)))]'
            : 'border-line group-data-[collapsible=icon]:w-(--sidebar-width-icon) group-data-[side=left]:border-r group-data-[side=right]:border-l',
          props.class,
        )
      "
      v-bind="$attrs"
    >
      <div
        data-sidebar="sidebar"
        data-slot="sidebar-inner"
        :class="
          cn(
            'flex size-full flex-col gap-8 overflow-x-hidden bg-surface-subtle px-4 py-6',
            'group-data-[variant=floating]:rounded-lg group-data-[variant=floating]:border group-data-[variant=floating]:border-line',
          )
        "
      >
        <slot />
      </div>
    </div>
  </div>
</template>
