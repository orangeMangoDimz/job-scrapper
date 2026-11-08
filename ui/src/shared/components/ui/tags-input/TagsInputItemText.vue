<script setup lang="ts">
import type { TagsInputItemTextProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import { reactiveOmit } from '@vueuse/core'
import { TagsInputItemText, useForwardProps } from 'reka-ui'
import { cn } from '@/shared/utils/cn'

const props = defineProps<TagsInputItemTextProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = reactiveOmit(props, 'class')
const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <TagsInputItemText
    data-slot="tags-input-item-text"
    v-bind="forwarded"
    :class="cn('truncate', props.class)"
  >
    <slot />
  </TagsInputItemText>
</template>
