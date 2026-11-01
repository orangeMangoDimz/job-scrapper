<script setup lang="ts">
import type { PrimitiveProps } from 'reka-ui'
import type { HTMLAttributes } from 'vue'
import type { BadgeVariants } from '.'
import { Primitive } from 'reka-ui'
import { cn } from '@/shared/utils/cn'
import { badgeVariants } from '.'

interface Props extends PrimitiveProps {
  tone?: BadgeVariants['tone']
  class?: HTMLAttributes['class']
}

const props = withDefaults(defineProps<Props>(), {
  as: 'span',
  tone: 'neutral',
})
</script>

<template>
  <Primitive
    data-slot="badge"
    :data-tone="tone"
    :as="as"
    :as-child="asChild"
    :class="cn(badgeVariants({ tone }), props.class)"
  >
    <slot />
  </Primitive>
</template>
