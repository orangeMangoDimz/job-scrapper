<script lang="ts" setup>
import type { ToasterProps } from 'vue-sonner'

import {
  CircleCheckIcon,
  InfoIcon,
  Loader2Icon,
  OctagonXIcon,
  TriangleAlertIcon,
  XIcon,
} from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import { Toaster as Sonner } from 'vue-sonner'
import 'vue-sonner/style.css'
import { cn } from '@/shared/utils/cn'

const props = withDefaults(defineProps<ToasterProps>(), {
  position: 'bottom-center',
  closeButton: true,
  closeButtonPosition: 'top-right',
  visibleToasts: 3,
})
const delegatedProps = reactiveOmit(props, 'class', 'toastOptions')

const defaultClasses = {
  toast:
    'pointer-events-auto flex w-(--width) items-center gap-4 rounded-lg bg-ink py-3 pr-3 pl-5 text-body-sm text-surface shadow-lg',
  content: 'flex min-w-0 flex-1 flex-col gap-1',
  title: 'text-body-sm font-medium',
  description: 'text-body-sm text-surface',
  icon: 'flex size-5 shrink-0 items-center justify-center',
  actionButton:
    'shrink-0 cursor-pointer rounded-sm bg-transparent p-0 text-body-sm font-semibold whitespace-nowrap text-surface underline outline-none focus-visible:focus-ring',
  cancelButton:
    'shrink-0 cursor-pointer rounded-sm bg-transparent p-0 text-body-sm font-medium whitespace-nowrap text-surface outline-none focus-visible:focus-ring',
  closeButton:
    'order-last flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-full border-0 bg-transparent p-0 text-surface press outline-none hover:bg-surface/15 focus-visible:focus-ring',
}
</script>

<template>
  <Sonner
    :class="cn('toaster group', props.class)"
    :style="{
      '--normal-bg': 'var(--ink)',
      '--normal-text': 'var(--surface)',
      '--normal-border': 'var(--ink)',
      '--border-radius': 'var(--radius-lg)',
      '--width': '28rem',
      fontFamily: 'var(--font-sans)',
    }"
    :toast-options="{
      unstyled: true,
      closeButtonAriaLabel: 'Dismiss',
      ...props.toastOptions,
      classes: { ...defaultClasses, ...props.toastOptions?.classes },
    }"
    v-bind="delegatedProps"
  >
    <template #success-icon>
      <CircleCheckIcon class="size-5" />
    </template>
    <template #info-icon>
      <InfoIcon class="size-5" />
    </template>
    <template #warning-icon>
      <TriangleAlertIcon class="size-5" />
    </template>
    <template #error-icon>
      <OctagonXIcon class="size-5" />
    </template>
    <template #loading-icon>
      <div>
        <Loader2Icon class="size-5 animate-spin" />
      </div>
    </template>
    <template #close-icon>
      <XIcon class="size-4" />
    </template>
  </Sonner>
</template>
