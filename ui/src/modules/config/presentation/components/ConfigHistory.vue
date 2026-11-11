<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { toast } from 'vue-sonner'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import EmptyState from '@/shared/components/EmptyState.vue'
import PageSection from '@/shared/components/PageSection.vue'
import ShowMoreToggle from '@/shared/components/ShowMoreToggle.vue'
import { Button } from '@/shared/components/ui/button'
import { useCollapsibleList } from '@/shared/composables/useCollapsibleList'

const RESTORED_MESSAGE = 'Version restored'

const store = useConfigStore()
const pendingVersion = ref<number | null>(null)
const isLocked = computed(() => store.isRestoring || (store.snapshot?.isStale ?? true))
const listId = useId()
const {
  isExpanded,
  hiddenCount,
  visibleItems: visibleHistory,
  toggle,
} = useCollapsibleList(() => store.history)

watch(isExpanded, (expanded) => {
  if (!expanded) {
    pendingVersion.value = null
  }
})

function toLocalTime(timestamp: string): string {
  return new Date(timestamp).toLocaleString()
}

async function confirmRestore(version: number): Promise<void> {
  pendingVersion.value = null
  if (await store.restore(version)) {
    toast.success(RESTORED_MESSAGE)
  }
}
</script>

<template>
  <PageSection title="Older versions">
    <p v-if="store.historyError" role="alert" class="text-body-sm text-danger">
      {{ store.historyError }}
    </p>
    <EmptyState
      v-else-if="store.history.length === 0"
      compact
      title="No older versions yet."
      hint="Each save keeps the previous version here."
    />
    <div v-else class="flex flex-col gap-4 md:gap-3">
      <ul :id="listId" class="flex flex-col gap-4 md:gap-3">
        <li
          v-for="entry in visibleHistory"
          :key="entry.version"
          class="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line p-4"
        >
          <div class="flex min-w-0 flex-col">
            <span class="text-body-sm font-semibold text-ink">
              Version {{ entry.version }}, {{ toLocalTime(entry.updatedAt) }}, by
              {{ entry.updatedBy }}
            </span>
            <span class="text-body-sm text-ink-muted">{{ entry.keywords.join(', ') }}</span>
            <span class="text-body-sm text-ink-muted">{{ entry.enabledSites.join(', ') }}</span>
          </div>
          <div v-if="pendingVersion === entry.version" class="flex gap-2">
            <Button type="button" :disabled="isLocked" @click="confirmRestore(entry.version)">
              Confirm restore
            </Button>
            <Button type="button" variant="secondary" @click="pendingVersion = null">Cancel</Button>
          </div>
          <Button
            v-else
            type="button"
            variant="secondary"
            :disabled="isLocked"
            @click="pendingVersion = entry.version"
          >
            Restore
          </Button>
        </li>
      </ul>
      <ShowMoreToggle
        v-if="hiddenCount > 0"
        :controls="listId"
        :is-expanded="isExpanded"
        :hidden-count="hiddenCount"
        @toggle="toggle"
      />
    </div>
  </PageSection>
</template>
