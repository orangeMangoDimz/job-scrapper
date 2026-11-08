<script setup lang="ts">
import type { TagsInputRootEmits, TagsInputRootProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { TagsInputRoot, useForwardPropsEmits } from 'reka-ui'
import { cn } from '@/shared/utils/cn'

const props = defineProps<TagsInputRootProps & { class?: HTMLAttributes['class'] }>()
const emits = defineEmits<TagsInputRootEmits>()

const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <TagsInputRoot
    v-slot="slotProps"
    data-slot="tags-input"
    v-bind="forwarded"
    :class="
      cn(
        'flex min-h-10 w-full min-w-0 flex-wrap items-center gap-2 rounded-md border border-line-strong bg-surface px-2 py-1.5 text-body text-ink transition-colors duration-150 focus-within:border-accent focus-within:focus-ring data-disabled:cursor-not-allowed data-disabled:bg-surface-subtle data-disabled:text-ink-muted',
        props.class,
      )
    "
  >
    <slot v-bind="slotProps" />
  </TagsInputRoot>
</template>
