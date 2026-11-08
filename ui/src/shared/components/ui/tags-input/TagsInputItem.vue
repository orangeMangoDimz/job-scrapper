<script setup lang="ts">
import type { TagsInputItemProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { TagsInputItem, useForwardProps } from 'reka-ui'
import { cn } from '@/shared/utils/cn'

const props = defineProps<TagsInputItemProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <TagsInputItem
    data-slot="tags-input-item"
    v-bind="forwarded"
    :class="
      cn(
        'inline-flex h-7 items-center gap-1 rounded-full border border-transparent bg-accent-soft pr-1 pl-3 text-body-sm font-medium text-accent ring-0 data-[state=active]:border-accent data-disabled:opacity-60',
        props.class,
      )
    "
  >
    <slot />
  </TagsInputItem>
</template>
