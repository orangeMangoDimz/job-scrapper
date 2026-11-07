<script setup lang="ts">
import type { HTMLAttributes, Ref } from 'vue'
import { useMediaQuery, useVModel } from '@vueuse/core'
import { TooltipProvider } from 'reka-ui'
import { computed, ref } from 'vue'
import { cn } from '@/shared/utils/cn'
import { provideSidebarContext, SIDEBAR_WIDTH, SIDEBAR_WIDTH_ICON } from './utils'

const props = withDefaults(
  defineProps<{
    defaultOpen?: boolean
    open?: boolean
    class?: HTMLAttributes['class']
  }>(),
  {
    defaultOpen: true,
    open: undefined,
  },
)

const emits = defineEmits<{
  'update:open': [open: boolean]
}>()

const isMobile = useMediaQuery('(max-width: 767px)')
const openMobile = ref(false)

const open = useVModel(props, 'open', emits, {
  defaultValue: props.defaultOpen ?? false,
  passive: (props.open === undefined) as false,
}) as Ref<boolean>

function setOpen(value: boolean) {
  open.value = value
}

function setOpenMobile(value: boolean) {
  openMobile.value = value
}

function toggleSidebar() {
  return isMobile.value ? setOpenMobile(!openMobile.value) : setOpen(!open.value)
}

const state = computed(() => (open.value ? 'expanded' : 'collapsed'))

provideSidebarContext({
  state,
  open,
  setOpen,
  isMobile,
  openMobile,
  setOpenMobile,
  toggleSidebar,
})
</script>

<template>
  <TooltipProvider :delay-duration="0">
    <div
      data-slot="sidebar-wrapper"
      :style="{
        '--sidebar-width': SIDEBAR_WIDTH,
        '--sidebar-width-icon': SIDEBAR_WIDTH_ICON,
        '--sidebar-content-width': `calc(${SIDEBAR_WIDTH} - 2rem)`,
      }"
      :class="
        cn(
          'group/sidebar-wrapper has-data-[variant=inset]:bg-surface-subtle flex min-h-svh w-full',
          props.class,
        )
      "
      v-bind="$attrs"
    >
      <slot />
    </div>
  </TooltipProvider>
</template>
