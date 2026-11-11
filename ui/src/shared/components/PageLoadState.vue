<script setup lang="ts">
import { CircleAlert } from '@lucide/vue'
import { Button } from '@/shared/components/ui/button'
import { Skeleton } from '@/shared/components/ui/skeleton'

defineProps<{
  isError: boolean
  loadingLabel: string
  errorTitle: string
  errorMessage: string | null
}>()

const emit = defineEmits<{
  retry: []
}>()
</script>

<template>
  <div v-if="isError" class="flex flex-1 flex-col items-center justify-center self-stretch">
    <div role="alert" class="flex max-w-reading flex-col items-center gap-2 text-center">
      <CircleAlert class="size-5 text-ink-muted" aria-hidden="true" />
      <h3 class="text-heading text-ink">{{ errorTitle }}</h3>
      <p v-if="errorMessage" class="text-body-sm text-ink-muted">{{ errorMessage }}</p>
      <Button variant="primary" class="mt-4" @click="emit('retry')">Try again</Button>
    </div>
  </div>

  <div v-else data-slot="page-skeleton" class="flex flex-1 flex-col gap-6 self-stretch">
    <p role="status" class="sr-only">{{ loadingLabel }}</p>
    <slot>
      <Skeleton class="h-9 w-56" />
      <Skeleton class="h-24 w-full rounded-lg" />
      <Skeleton class="h-24 w-full rounded-lg" />
      <Skeleton class="h-24 w-full rounded-lg" />
    </slot>
  </div>
</template>
