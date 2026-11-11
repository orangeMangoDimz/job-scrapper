<script setup lang="ts">
import { ChevronDown, ChevronUp } from '@lucide/vue'
import { Button } from '@/shared/components/ui/button'

defineProps<{ controls: string; isExpanded: boolean; hiddenCount: number }>()
const emit = defineEmits<{ toggle: [] }>()
</script>

<template>
  <Button
    type="button"
    variant="ghost"
    size="sm"
    class="self-center"
    :aria-controls="controls"
    :aria-expanded="isExpanded"
    @click="emit('toggle')"
  >
    <template v-if="isExpanded">Show less <ChevronUp aria-hidden="true" /></template>
    <template v-else>Show {{ hiddenCount }} more <ChevronDown aria-hidden="true" /></template>
  </Button>
</template>
