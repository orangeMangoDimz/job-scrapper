<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { isNavigationFailure, NavigationFailureType, useRoute, useRouter } from 'vue-router'
import { ChevronDown, ChevronUp } from '@lucide/vue'
import ConfigForm from '@/modules/config/presentation/components/ConfigForm.vue'
import {
  readConfigCardOpen,
  writeConfigCardOpen,
} from '@/modules/config/presentation/components/configCardStorage'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import PageLoadState from '@/shared/components/PageLoadState.vue'
import PageSection from '@/shared/components/PageSection.vue'
import { Button } from '@/shared/components/ui/button'
import { Skeleton } from '@/shared/components/ui/skeleton'

const CONFIG_HASH = '#config'

const store = useConfigStore()
const route = useRoute()
const router = useRouter()
const isOpen = ref(readConfigCardOpen())
const bodyId = useId()
const savedNote = computed(() => {
  const snapshot = store.snapshot
  if (snapshot === null) {
    return undefined
  }
  const savedAt = new Date(snapshot.updatedAt).toLocaleString()
  return `Version ${snapshot.version}, saved ${savedAt} by ${snapshot.updatedBy}. Changes apply from the next run`
})

function setOpen(next: boolean): void {
  isOpen.value = next
  writeConfigCardOpen(next)
}

function toggle(): void {
  setOpen(!isOpen.value)
}

if (route.hash === CONFIG_HASH) {
  setOpen(true)
}

const stopListening = router.afterEach((to, _from, failure) => {
  const isDuplicate = isNavigationFailure(failure, NavigationFailureType.duplicated)
  if (to.hash === CONFIG_HASH && (!failure || isDuplicate)) {
    setOpen(true)
  }
})

onBeforeUnmount(stopListening)

onMounted(() => {
  if (store.status === 'idle') {
    void store.load()
    void store.loadHistory()
  }
})
</script>

<template>
  <PageSection title="Config" :description="savedNote">
    <template #actions>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        :aria-label="isOpen ? 'Hide config' : 'Show config'"
        :aria-controls="bodyId"
        :aria-expanded="isOpen"
        @click="toggle"
      >
        <ChevronUp v-if="isOpen" aria-hidden="true" />
        <ChevronDown v-else aria-hidden="true" />
      </Button>
    </template>
    <div v-if="isOpen" :id="bodyId" class="flex min-w-0 flex-col gap-6 md:gap-4">
      <PageLoadState
        v-if="store.values === null"
        :is-error="store.status === 'error'"
        loading-label="Loading config"
        error-title="Could not load config"
        :error-message="store.errorMessage"
        @retry="store.load"
      >
        <div class="flex flex-col gap-6 md:gap-4">
          <Skeleton v-for="index in 3" :key="index" class="h-48 w-full rounded-lg" />
        </div>
      </PageLoadState>
      <ConfigForm v-else :is-save-bar-sticky="false" />
    </div>
  </PageSection>
</template>
