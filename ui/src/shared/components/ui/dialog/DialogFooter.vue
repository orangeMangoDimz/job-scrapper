<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { DialogClose } from 'reka-ui'
import { cn } from '@/shared/utils/cn'
import { Button } from '@/shared/components/ui/button'

const props = withDefaults(
  defineProps<{
    class?: HTMLAttributes['class']
    showCloseButton?: boolean
  }>(),
  {
    showCloseButton: false,
  },
)
</script>

<template>
  <div
    data-slot="dialog-footer"
    :class="cn('mt-auto flex flex-wrap justify-end gap-2', props.class)"
  >
    <slot />
    <DialogClose v-if="showCloseButton" as-child>
      <Button variant="secondary"> Close </Button>
    </DialogClose>
  </div>
</template>
