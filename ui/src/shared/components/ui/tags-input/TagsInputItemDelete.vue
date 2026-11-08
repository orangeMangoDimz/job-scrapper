<script setup lang="ts">
import type { TagsInputItemDeleteProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { XIcon } from '@lucide/vue'
import { reactiveOmit } from '@vueuse/core'
import { TagsInputItemDelete, useForwardProps } from 'reka-ui'
import { cn } from '@/shared/utils/cn'

const props = defineProps<TagsInputItemDeleteProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <TagsInputItemDelete
    data-slot="tags-input-item-delete"
    v-bind="forwarded"
    :class="
      cn(
        'flex size-5 shrink-0 cursor-pointer items-center justify-center rounded-full text-current outline-none transition-colors duration-150 hover:bg-line focus-visible:focus-ring',
        props.class,
      )
    "
  >
    <slot>
      <XIcon class="size-3.5" />
    </slot>
  </TagsInputItemDelete>
</template>
