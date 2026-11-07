<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { cn } from '@/shared/utils/cn'
import { Input } from '@/shared/components/ui/input'

const props = defineProps<{
  class?: HTMLAttributes['class']
}>()
</script>

<template>
  <Input data-slot="sidebar-input" data-sidebar="input" :class="cn('h-8 w-full', props.class)">
    <slot />
  </Input>
</template>
